"""최소 세탁 계획과 실제 설정 검증 API입니다."""

from fastapi import APIRouter

from backend.app.api.deps import CurrentOwner, DbSession
from backend.app.api.schemas import COMMON_ERROR_RESPONSES
from backend.app.planning.schemas import (
    PlanRequest,
    PlanResponse,
    SettingsValidateRequest,
    SettingsValidateResponse,
)
from backend.app.planning.service import create_plan, validate_settings

router = APIRouter(
    prefix="/api",
    tags=["planning"],
    responses=COMMON_ERROR_RESPONSES,
)


@router.post("/plans", response_model=PlanResponse, summary="최소 세탁 계획 계산")
def calculate_plan(
    payload: PlanRequest,
    db: DbSession,
    owner_id: CurrentOwner,
) -> PlanResponse:
    """의류를 분류하고 실제 지원 설정으로 최소 세탁 그룹을 계산합니다."""

    # 요청 식별값과 DB 스냅샷을 서비스에 그대로 전달합니다.
    return create_plan(db, owner_id, payload)


@router.post(
    "/settings/validate",
    response_model=SettingsValidateResponse,
    summary="실제 세탁기 설정 검증",
)
def validate_actual_settings(
    payload: SettingsValidateRequest,
    db: DbSession,
    owner_id: CurrentOwner,
) -> SettingsValidateResponse:
    """추천과 같은지가 아니라 실제 입력값이 안전한지 독립 검증합니다."""

    return validate_settings(db, owner_id, payload)
