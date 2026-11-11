"""사용자 기기 등록과 재조회 API입니다."""

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.api.deps import CurrentOwner, DbSession
from backend.app.api.schemas import COMMON_ERROR_RESPONSES, UserMachineCreate, UserMachineRead
from backend.app.core.errors import ApiError
from backend.app.db.models import MachineModel, UserMachine

router = APIRouter(
    prefix="/api/user-machines",
    tags=["user-machines"],
    responses=COMMON_ERROR_RESPONSES,
)


@router.post(
    "",
    response_model=UserMachineRead,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 기기 등록",
)
def create_user_machine(
    payload: UserMachineCreate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> UserMachine:
    """공용 모델 참조 또는 사용자 수동 입력을 소유자에게 귀속합니다."""

    # 모델 ID가 있으면 실제 공용 모델이 존재하는지 먼저 확인합니다.
    machine_model = None
    if payload.machine_model_id:
        machine_model = db.scalar(
            select(MachineModel).where(MachineModel.id == payload.machine_model_id)
        )
        # 존재하지 않는 공용 모델을 저장하면 재조회 시 연결이 깨지므로 거부합니다.
        if machine_model is None:
            raise ApiError("MACHINE_NOT_FOUND", "선택한 기기 모델을 찾을 수 없습니다.", 404)
        # 공용 모델의 종류와 등록 요청 종류가 다르면 잘못된 연결이 됩니다.
        if machine_model.machine_type != payload.machine_type:
            raise ApiError(
                "MACHINE_TYPE_MISMATCH",
                "등록 기기 종류와 공용 모델 종류가 다릅니다.",
                422,
                {"field": "machine_type"},
            )
    # 수동 입력은 별도 JSON 칼럼에 저장해 공용 모델을 변경하지 않습니다.
    user_machine = UserMachine(owner_id=owner_id, **payload.model_dump())
    # 세션에 등록해 INSERT를 준비합니다.
    db.add(user_machine)
    # 트랜잭션을 확정합니다.
    db.commit()
    # 생성된 ID와 시각을 포함한 저장 결과를 읽습니다.
    db.refresh(user_machine)
    # 관계를 응답에 담을 때 사용할 수 있도록 공용 모델을 연결합니다.
    user_machine.machine_model = machine_model
    return user_machine


@router.get("", response_model=list[UserMachineRead], summary="사용자 기기 재조회")
def list_user_machines(db: DbSession, owner_id: CurrentOwner) -> list[UserMachine]:
    """현재 소유자의 등록 기기를 다시 읽어 앱 복원을 지원합니다."""

    # 연결된 공식 모델도 함께 읽어 응답에서 모델 참조 상태를 보여줍니다.
    statement = (
        select(UserMachine)
        .options(selectinload(UserMachine.machine_model))
        .where(UserMachine.owner_id == owner_id)
        .order_by(UserMachine.created_at.desc())
    )
    # 신규 사용자는 빈 배열을 받도록 합니다.
    return list(db.scalars(statement).all())
