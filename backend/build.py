"""Python 백엔드의 문법과 앱 계약을 검사하는 빌드 진입점입니다."""

from pathlib import Path


def main() -> None:
    """외부 DB에 쓰지 않고 Python 소스와 OpenAPI 구성을 검증합니다."""

    # 프로젝트 루트를 기준으로 실행해 호출 위치에 따른 차이를 줄입니다.
    root = Path(__file__).resolve().parent.parent
    # 앱과 마이그레이션의 Python 파일을 모두 검사합니다.
    sources = sorted((root / "backend").rglob("*.py"))
    # 마이그레이션도 배포에 필요한 소스이므로 함께 검사합니다.
    sources += sorted((root / "migrations").rglob("*.py"))
    # 문법 검사는 코드를 실행하거나 DB 데이터를 변경하지 않습니다.
    for source in sources:
        # 파일명을 전달하면 문법 오류가 발생한 위치를 정확히 알 수 있습니다.
        compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")
    # 실제 앱을 가져와 드라이버와 라우터 의존성이 준비됐는지 확인합니다.
    from backend.app.main import app

    # OpenAPI 생성까지 수행해 모델과 라우터 등록 오류를 찾습니다.
    schema = app.openapi()
    # 빌드가 성공해도 핵심 API가 빠지는 일을 방지합니다.
    assert "/api/wardrobe" in schema["paths"]
    # 연결 주소나 비밀번호는 출력하지 않고 검사 건수만 표시합니다.
    print(f"BUILD OK: {len(sources)} Python files; {len(schema['paths'])} API paths")


# npm run build와 Python 모듈 실행이 같은 검사를 수행하게 합니다.
if __name__ == "__main__":
    main()
