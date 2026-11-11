"""환경 변수 기반 서버 설정을 한 곳에서 관리합니다."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """서버가 시작될 때 읽는 환경 설정입니다."""

    # 앱 이름은 FastAPI 문서와 로그에서 서버를 구분하기 위해 사용합니다.
    app_name: str = "WashWise Backend"
    # 현재 구현은 인증이 없는 데모 모드만 지원하므로 모드를 명시적으로 기록합니다.
    app_mode: Literal["demo", "production"] = "demo"
    # 데모 요청에 서버가 자동으로 지정할 소유자 ID입니다.
    demo_owner_id: str = "demo-user"
    # 로컬 기본값은 별도 서버가 필요 없는 SQLite로 두고 운영에서는 Neon URL을 주입합니다.
    database_url: str = "sqlite:///./washwise.db"
    # 마이그레이션은 PgBouncer를 거치지 않는 직접 연결을 사용합니다.
    database_url_unpooled: str | None = None
    # AI 담당 라우터가 준비된 경우에만 선택적으로 공용 앱에 연결합니다.
    enable_ai_router: bool = False
    # 브라우저 기반 데모에서 허용할 주소를 쉼표로 입력받습니다.
    cors_allow_origins: str = "http://localhost:3000,http://localhost:8081"
    # 로그 레벨은 운영 환경에서 환경 변수로 조절할 수 있습니다.
    log_level: str = "INFO"

    # `.env`를 읽되 정의되지 않은 추가 값은 무시해 배포 환경의 공통 변수를 허용합니다.
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", "database_url_unpooled", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: str | None) -> str | None:
        """Neon의 표준 URL을 이미 설치된 psycopg 3 드라이버에 연결합니다."""

        # 비어 있는 선택 URL은 그대로 두어 로컬 SQLite 실행을 유지합니다.
        if value is None:
            return None
        # 비밀번호 등을 다시 조립하지 않고 URL의 드라이버 접두사만 변경합니다.
        for prefix in ("postgres://", "postgresql://"):
            # 명시적인 다른 드라이버나 SQLite URL은 변경하지 않습니다.
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        # 기존에 드라이버가 지정된 URL은 원래 설정을 보존합니다.
        return value

    @property
    def migration_database_url(self) -> str:
        """직접 연결이 제공되면 마이그레이션에 우선 적용합니다."""

        # 로컬에서는 별도 직접 URL이 없으므로 기존 DB 주소를 사용합니다.
        return self.database_url_unpooled or self.database_url

    @property
    def cors_origins(self) -> list[str]:
        """쉼표로 입력된 CORS 주소를 공백 없이 목록으로 바꿉니다."""

        # 빈 항목은 브라우저 보안 설정에 들어가면 안 되므로 제거합니다.
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 모든 요청이 같은 값을 사용하게 합니다."""

    # 캐시된 설정은 프로세스 시작 후 환경 변수가 바뀌어도 일관성을 유지합니다.
    return Settings()
