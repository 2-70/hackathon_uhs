"""공용 기기 모델과 확인된 코스 설정 조회 API입니다."""

from fastapi import APIRouter, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from backend.app.api.deps import DbSession
from backend.app.api.schemas import (
    COMMON_ERROR_RESPONSES,
    MachineCourseRead,
    MachineCoursesResponse,
    MachineModelSummary,
)
from backend.app.core.errors import ApiError
from backend.app.db.models import MachineCourse, MachineModel

router = APIRouter(
    prefix="/api/machines",
    tags=["machines"],
    responses=COMMON_ERROR_RESPONSES,
)


@router.get("", response_model=list[MachineModelSummary], summary="공용 기기 모델 검색")
def list_machine_models(
    db: DbSession,
    query: str | None = Query(default=None, min_length=1, max_length=100),
    machine_type: str | None = Query(default=None, min_length=1, max_length=40),
) -> list[MachineModel]:
    """제조사·모델명 또는 기기 종류로 공용 모델을 검색합니다."""

    # 기본 조회는 모든 모델을 반환하고 선택 필터가 있을 때만 WHERE 조건을 추가합니다.
    statement = select(MachineModel).order_by(MachineModel.manufacturer, MachineModel.model_name)
    # 검색어는 사용자가 입력한 문자열을 제조사·모델명·안정 키에 적용합니다.
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                MachineModel.manufacturer.ilike(pattern),
                MachineModel.model_name.ilike(pattern),
                MachineModel.machine_key.ilike(pattern),
            )
        )
    # washer 같은 종류 필터는 검색 결과를 모바일 선택 UI에 맞게 줄입니다.
    if machine_type:
        statement = statement.where(MachineModel.machine_type == machine_type)
    # 공식 모델은 공용 데이터이므로 소유자 조건 없이 읽습니다.
    return list(db.scalars(statement).all())


@router.get(
    "/{machine_id}/courses",
    response_model=MachineCoursesResponse,
    summary="기기 모델의 코스와 지원 설정 조합 조회",
)
def list_machine_courses(machine_id: str, db: DbSession) -> MachineCoursesResponse:
    """선택한 모델에 실제로 확인된 코스별 설정 조합만 반환합니다."""

    # 코스와 설정을 한 번에 읽어 반복적인 lazy load를 줄입니다.
    statement = (
        select(MachineModel)
        .options(selectinload(MachineModel.courses).selectinload(MachineCourse.settings))
        .where(MachineModel.id == machine_id)
    )
    # ID가 없는 모델은 코스도 없으므로 명시적인 404를 반환합니다.
    machine = db.scalar(statement)
    if machine is None:
        raise ApiError("MACHINE_NOT_FOUND", "기기 모델을 찾을 수 없습니다.", 404)
    # 응답 모델에 ORM 관계를 담아 코스와 조합을 그대로 직렬화합니다.
    return MachineCoursesResponse(
        machine=MachineModelSummary.model_validate(machine),
        courses=[MachineCourseRead.model_validate(course) for course in machine.courses],
    )
