"""Neon URL과 마이그레이션 연결 선택이 기존 설정을 보존하는지 검사합니다."""

from backend.app.core.config import Settings


def test_neon_urls_use_psycopg_and_direct_migrations():
    """앱용 pooled URL과 마이그레이션용 direct URL을 구분합니다."""

    # 실제 비밀번호가 없는 테스트 주소로 Neon의 환경변수 형식을 재현합니다.
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:fake@demo-pooler.neon.tech/neondb?sslmode=require",
        database_url_unpooled="postgres://user:fake@demo.neon.tech/neondb?sslmode=require",
    )
    # 새 드라이버를 추가하지 않고 기존 psycopg 3가 선택되어야 합니다.
    assert settings.database_url.startswith("postgresql+psycopg://")
    # 암호화 옵션은 접두사 변환 후에도 유지되어야 합니다.
    assert settings.database_url.endswith("?sslmode=require")
    # 마이그레이션에 앱용 pooler 주소가 선택되면 안 됩니다.
    assert "-pooler" not in settings.migration_database_url


def test_local_sqlite_keeps_its_original_url():
    """Neon 연결 지원을 추가해도 로컬 개발 주소는 유지합니다."""

    # 환경 파일을 사용하지 않아 테스트가 실제 Neon DB를 참조하지 않게 합니다.
    settings = Settings(_env_file=None, database_url="sqlite://", database_url_unpooled=None)
    # 직접 연결 주소가 없으면 동일한 로컬 DB로 마이그레이션합니다.
    assert settings.migration_database_url == "sqlite://"
