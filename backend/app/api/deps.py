"""라우터에서 공유하는 의존성입니다."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.errors import ApiError
from backend.app.db.session import get_db


def get_current_owner_id() -> str:
    """현재는 인증 대신 명시된 데모 소유자를 반환합니다."""

    # 설정을 통해 모든 조회·변경 API가 같은 소유자 정책을 사용하게 합니다.
    settings = get_settings()
    # production을 인증이 있는 것처럼 가장하지 않고 아직 준비되지 않았음을 알립니다.
    if settings.app_mode != "demo":
        raise ApiError(
            code="AUTH_NOT_CONFIGURED",
            message="공개 서비스 인증이 아직 설정되지 않았습니다.",
            status_code=503,
        )
    # 클라이언트가 소유자 ID를 임의로 보내지 못하도록 서버 설정값만 사용합니다.
    return settings.demo_owner_id


# 라우터 매개변수에서 `Depends(get_db)`를 반복하지 않도록 읽기 쉬운 타입 별칭을 만듭니다.
DbSession = Annotated[Session, Depends(get_db)]
# 현재 소유자 의존성도 타입으로 묶어 모든 도메인 API가 같은 정책을 사용하게 합니다.
CurrentOwner = Annotated[str, Depends(get_current_owner_id)]
