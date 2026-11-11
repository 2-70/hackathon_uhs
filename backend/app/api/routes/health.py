"""서버와 데이터베이스 상태 확인 API입니다."""

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.api.deps import DbSession
from backend.app.api.schemas import COMMON_ERROR_RESPONSES, HealthResponse
from backend.app.core.config import get_settings
from backend.app.core.errors import ApiError

router = APIRouter(tags=["health"], responses=COMMON_ERROR_RESPONSES)


@router.get("/health", response_model=HealthResponse, summary="서버 상태 확인")
def read_health() -> HealthResponse:
    """DB 마이그레이션 여부와 관계없이 서버 프로세스가 살아 있는지 확인합니다."""

    # 설정을 읽어 데모 모드가 응답에 명시되도록 합니다.
    settings = get_settings()
    # DB를 확인하지 않는 상태 응답은 마이그레이션 전에도 사용할 수 있습니다.
    return HealthResponse(status="ok", mode=settings.app_mode)


@router.get("/health/db", response_model=HealthResponse, summary="데이터베이스 연결 확인")
def read_database_health(db: DbSession) -> HealthResponse:
    """DB에 SELECT 1을 보내 연결이 실제로 가능한지 확인합니다."""

    try:
        # 데이터베이스 드라이버와 연결 풀까지 포함한 최소 왕복을 검사합니다.
        db.execute(text("SELECT 1"))
    except Exception as exc:
        # 내부 연결 문자열이나 드라이버 오류는 응답에 노출하지 않습니다.
        raise ApiError(
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스에 연결할 수 없습니다.",
            status_code=503,
        ) from exc
    # 정상 연결이면 서버와 DB가 모두 준비된 상태를 반환합니다.
    return HealthResponse(status="ok", mode=get_settings().app_mode, database="ok")
