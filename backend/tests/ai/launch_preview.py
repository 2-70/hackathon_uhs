import asyncio
import os
import socket
import subprocess
import sys
import webbrowser
from getpass import getpass
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen

from backend.app.ai.connection import check_connection
from backend.app.ai.gemini import DEFAULT_MODEL, GeminiError

HOST = "127.0.0.1"
BACKEND = Path(__file__).resolve().parents[2]
WATCHED_PATHS = ((BACKEND / "app", "*.py"), (BACKEND / "seed" / "verified", "*.json"))


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


def start_server(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-B", "-m", "uvicorn", "backend.app.ai.preview:app", "--host", HOST, "--port", str(port)],
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


def run_preview(port: int) -> int:
    snapshot = watched_files()
    server = start_server(port)
    try:
        while server.poll() is None:
            sleep(0.5)
            current_files = watched_files()
            if current_files != snapshot:
                snapshot = current_files
                print("백엔드 파일이 바뀌었어요. 같은 주소에서 서버를 다시 시작합니다.", flush=True)
                stop_server(server)
                server = start_server(port)
        return server.returncode or 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop_server(server)


def ensure_connection() -> bool:
    while True:
        try:
            if not os.getenv("GEMINI_API_KEY", "").strip():
                if not sys.stdin.isatty():
                    print("터미널에서 실행해 Gemini API 키를 입력해 주세요.", file=sys.stderr)
                    return False
                api_key = getpass("Gemini API 키를 입력해 주세요: ").strip()
                if not api_key:
                    print("Gemini API 키가 비어 있어요.", file=sys.stderr)
                    continue
                os.environ["GEMINI_API_KEY"] = api_key
            print("Gemini가 실제로 응답하는지 확인 중입니다 (최대 25초)...", flush=True)
            asyncio.run(check_connection(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODEL") or DEFAULT_MODEL))
            print("Gemini 응답을 확인했어요. 사진 테스트 화면을 엽니다.", flush=True)
            return True
        except GeminiError as error:
            print(str(error), file=sys.stderr)
            if not sys.stdin.isatty():
                return False
            if error.code in {"analysis_key_invalid", "analysis_key_leaked", "analysis_key_restricted", "analysis_access_denied"}:
                os.environ.pop("GEMINI_API_KEY", None)
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


def main() -> int:
    if not ensure_connection():
        return 1
    try:
        port = available_port()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    server_url = f"http://{HOST}:{port}"
    docs_url = f"{server_url}/docs#/ai/analyze_photo_api_analyze_post"
    print(f"테스트 화면 {docs_url}", flush=True)
    Thread(target=open_when_ready, args=(server_url, docs_url), daemon=True).start()
    return run_preview(port)


if __name__ == "__main__":
    raise SystemExit(main())
