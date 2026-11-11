import asyncio
import os
import shutil
import socket
import subprocess
import sys
import webbrowser
from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen

from backend.app.ai.connection import check_connection
from backend.app.ai.gemini import DEFAULT_MODEL, GeminiError, configured_gemini_keys

HOST = "127.0.0.1"
BACKEND = Path(__file__).resolve().parents[2]
WATCHED_PATHS = ((BACKEND / "app", "*.py"), (BACKEND / "seed" / "verified", "*.json"))
AI_PREVIEW = "backend.app.ai.preview:app"
WEB_PREVIEW = "backend.tests.ai.web_preview:app"


def available_port() -> int:
    for port in range(8000, 8010):
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("8000~8009번 포트가 사용 중이에요. 테스트 서버를 닫고 다시 실행해 주세요.")


def open_when_ready(server_url: str, docs_url: str) -> None:
    deadline = monotonic() + 15
    while monotonic() < deadline:
        try:
            with urlopen(f"{server_url}/openapi.json", timeout=1):
                pass
        except (URLError, TimeoutError):
            sleep(0.25)
            continue
        webbrowser.open(docs_url)
        return


def watched_files() -> dict[Path, int]:
    files = {}
    for directory, pattern in WATCHED_PATHS:
        for path in directory.rglob(pattern):
            try:
                files[path] = path.stat().st_mtime_ns
            except FileNotFoundError:
                continue
    return files


def start_server(port: int, application: str = AI_PREVIEW) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-B", "-m", "uvicorn", application, "--host", HOST, "--port", str(port)],
        cwd=BACKEND.parent,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def stop_server(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def run_preview(port: int, application: str = AI_PREVIEW) -> int:
    snapshot = watched_files()
    server = start_server(port, application)
    try:
        while server.poll() is None:
            sleep(0.5)
            current_files = watched_files()
            if current_files != snapshot:
                snapshot = current_files
                print("백엔드 파일이 바뀌었어요. 같은 주소에서 서버를 다시 시작합니다.", flush=True)
                stop_server(server)
                server = start_server(port, application)
        return server.returncode or 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop_server(server)


def ensure_connection() -> bool:
    keys = configured_gemini_keys()
    while True:
        try:
            if not keys:
                if not sys.stdin.isatty():
                    print("터미널에서 실행해 Gemini API 키를 입력해 주세요.", file=sys.stderr)
                    return False
                api_key = getpass("Gemini API 키를 입력해 주세요: ").strip()
                if not api_key:
                    print("Gemini API 키가 비어 있어요.", file=sys.stderr)
                    continue
                os.environ["GEMINI_API_KEY"] = api_key
                keys = (api_key,)
            for index, key in enumerate(keys, 1):
                print(f"Gemini 연결 확인 중 ({index}/{len(keys)})...", flush=True)
                try:
                    asyncio.run(check_connection(key, os.getenv("GEMINI_MODEL") or DEFAULT_MODEL))
                except GeminiError:
                    if index == len(keys):
                        raise
                    continue
                os.environ["GEMINI_API_KEY"] = key
                print("Gemini 응답을 확인했어요. 사진 테스트 화면을 엽니다.", flush=True)
                return True
        except GeminiError as error:
            print(str(error), file=sys.stderr)
            if not sys.stdin.isatty():
                return False
            if error.code in {"analysis_key_invalid", "analysis_key_leaked", "analysis_key_restricted", "analysis_access_denied"}:
                os.environ.pop("GEMINI_API_KEY", None)
                keys = ()
                print("다른 키를 입력하면 이 창에서 다시 확인합니다. 종료: Ctrl+C", flush=True)
            elif error.code == "analysis_model_unavailable":
                return False
            else:
                choice = input("Enter: 연결 다시 확인 / s: 사진 테스트 화면 열기 / q: 종료 > ").strip().lower()
                if choice == "s":
                    return True
                if choice == "q":
                    return False
        except (EOFError, KeyboardInterrupt):
            return False


def prepare_web_preview() -> None:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("웹 앱을 빌드하려면 pnpm이 필요해요.")

    root = BACKEND.parent
    preview_dir = root / ".tmp" / "app-preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    build_dir = preview_dir / "web"
    database_url = f"sqlite:///{(preview_dir / 'washwise.sqlite3').as_posix()}"
    preview_env = {
        "DATABASE_URL": database_url,
        "DATABASE_URL_UNPOOLED": database_url,
        "APP_MODE": "demo",
        "ENABLE_AI_ROUTER": "true",
        "WASHWISE_WEB_BUILD_DIR": str(build_dir),
    }
    # The web build talks to the backend on the same origin, regardless of the selected port.
    setup_env = {
        key: value for key, value in os.environ.items()
        if key not in {"GEMINI_API_KEY", "GEMINI_API_KEYS", "SERPAPI_API_KEY", "GOOGLE_CLOUD_VISION_API_KEY"}
    }
    setup_env.update(preview_env)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=setup_env, check=True)
    subprocess.run(
        [sys.executable, "-m", "backend.seed.load_verified", "--washwise-demo"],
        cwd=root, env=setup_env, check=True,
    )
    print("WashWise 웹 화면을 빌드합니다.", flush=True)
    subprocess.run(
        [pnpm, "exec", "expo", "export", "--platform", "web", "--output-dir", str(build_dir)],
        cwd=root / "mobile", env={**setup_env, "EXPO_PUBLIC_API_URL": "/"}, check=True,
    )
    os.environ.update(preview_env)


def main(web_app: bool = False, open_browser: bool = True) -> int:
    if web_app and not os.getenv("SERPAPI_API_KEY", "").strip() and sys.stdin.isatty():
        try:
            os.environ["SERPAPI_API_KEY"] = getpass("SerpApi API 키를 입력해 주세요: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 1
    if not ensure_connection():
        return 1
    try:
        if web_app:
            prepare_web_preview()
        port = available_port()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1

    server_url = f"http://{HOST}:{port}"
    page_url = server_url if web_app else f"{server_url}/docs#/ai/analyze_photo_api_analyze_post"
    print(f"테스트 화면 {page_url}", flush=True)
    if open_browser:
        Thread(target=open_when_ready, args=(server_url, page_url), daemon=True).start()
    return run_preview(port, WEB_PREVIEW if web_app else AI_PREVIEW)


if __name__ == "__main__":
    parser = ArgumentParser(description="WashWise 테스트 서버 실행")
    parser.add_argument("--app", action="store_true", help="WashWise 웹 화면과 전체 API를 함께 실행")
    parser.add_argument("--catalog-api-url", help="웹에서 조회할 기존 세탁기 카탈로그 API 주소")
    args = parser.parse_args()
    if args.catalog_api_url:
        os.environ["WASHWISE_CATALOG_API_URL"] = args.catalog_api_url
    raise SystemExit(main(web_app=args.app))
