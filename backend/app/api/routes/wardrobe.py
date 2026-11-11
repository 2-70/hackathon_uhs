"""옷장 등록·조회·수정·삭제 API입니다."""

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.api.deps import CurrentOwner, DbSession
from backend.app.api.schemas import (
    COMMON_ERROR_RESPONSES,
    DeleteResponse,
    WardrobeCreate,
    WardrobeRead,
    WardrobeUpdate,
)
from backend.app.core.errors import ApiError
from backend.app.db.models import WardrobeItem

router = APIRouter(
    prefix="/api/wardrobe",
    tags=["wardrobe"],
    responses=COMMON_ERROR_RESPONSES,
)


@router.post(
    "", response_model=WardrobeRead, status_code=status.HTTP_201_CREATED, summary="옷장 등록"
)
def create_wardrobe_item(
    payload: WardrobeCreate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> WardrobeItem:
    """현재 데모 사용자의 옷을 저장하고 저장된 값을 반환합니다."""

    # Pydantic이 검증한 요청을 SQLAlchemy 모델로 변환합니다.
    item = WardrobeItem(owner_id=owner_id, **payload.model_dump())
    # 세션에 추가해 INSERT 대상으로 등록합니다.
    db.add(item)
    try:
        # 이 API의 성공 경계를 명시적으로 커밋합니다.
        db.commit()
        # DB가 생성한 기본값과 시각을 포함하도록 최신 값을 읽습니다.
        db.refresh(item)
    except IntegrityError as exc:
        # 데이터 무결성 오류는 이 요청만 롤백하고 공통 오류로 변환합니다.
        db.rollback()
        raise ApiError("WARDROBE_CREATE_FAILED", "옷을 저장하지 못했습니다.", 409) from exc
    # 응답 모델이 ORM 객체를 읽어 저장 결과를 반환합니다.
    return item


@router.get("", response_model=list[WardrobeRead], summary="옷장 목록 조회")
def list_wardrobe_items(db: DbSession, owner_id: CurrentOwner) -> list[WardrobeItem]:
    """현재 소유자의 옷만 최신 등록 순서로 반환합니다."""

    # owner_id 조건을 항상 포함해 다른 소유자의 데이터가 섞이지 않게 합니다.
    statement = (
        select(WardrobeItem)
        .where(WardrobeItem.owner_id == owner_id)
        .order_by(WardrobeItem.created_at.desc())
    )
    # 결과가 없으면 빈 배열이 되어 신규 사용자의 정상 흐름을 지원합니다.
    return list(db.scalars(statement).all())


@router.get("/{item_id}", response_model=WardrobeRead, summary="옷장 단건 조회")
def get_wardrobe_item(
    item_id: str,
    db: DbSession,
    owner_id: CurrentOwner,
) -> WardrobeItem:
    """현재 소유자의 옷 한 건을 조회합니다."""

    # ID와 소유자를 함께 조건에 넣어 ID를 알아도 타인 데이터를 볼 수 없게 합니다.
    item = db.scalar(
        select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.owner_id == owner_id)
    )
    # 존재하지 않는 ID와 다른 소유자의 ID를 같은 404로 처리합니다.
    if item is None:
        raise ApiError("WARDROBE_NOT_FOUND", "옷장 항목을 찾을 수 없습니다.", 404)
    return item


@router.patch("/{item_id}", response_model=WardrobeRead, summary="옷장 수정")
def update_wardrobe_item(
    item_id: str,
    payload: WardrobeUpdate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> WardrobeItem:
    """전달된 필드만 현재 소유자의 옷장 항목에 반영합니다."""

    # 조회부터 소유자 조건을 적용해 수정 권한을 함께 확인합니다.
    item = db.scalar(
        select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.owner_id == owner_id)
    )
    # 존재하지 않는 항목은 수정할 수 없습니다.
    if item is None:
        raise ApiError("WARDROBE_NOT_FOUND", "옷장 항목을 찾을 수 없습니다.", 404)
    # PATCH에서 실제로 보낸 값만 추려 기존 값을 보존합니다.
    changes = payload.model_dump(exclude_unset=True)
    # 빈 PATCH는 성공처럼 보이지만 아무 것도 바꾸지 않으므로 입력 오류로 처리합니다.
    if not changes:
        raise ApiError("INVALID_INPUT", "수정할 필드를 하나 이상 입력해 주세요.", 422)
    # 허용된 필드만 모델에 대입하고 수정 시각은 SQLAlchemy가 갱신합니다.
    for field_name, value in changes.items():
        setattr(item, field_name, value)
    try:
        # 수정 내용을 저장합니다.
        db.commit()
        # 응답에 최신 DB 상태를 사용합니다.
        db.refresh(item)
    except IntegrityError as exc:
        # 실패한 수정은 롤백하여 일부 값만 남지 않게 합니다.
        db.rollback()
        raise ApiError("WARDROBE_UPDATE_FAILED", "옷장 항목을 수정하지 못했습니다.", 409) from exc
    return item


@router.delete("/{item_id}", response_model=DeleteResponse, summary="옷장 삭제")
def delete_wardrobe_item(
    item_id: str,
    db: DbSession,
    owner_id: CurrentOwner,
) -> DeleteResponse:
    """현재 소유자의 옷장 항목을 삭제합니다."""

    # 소유자 조건을 포함해 삭제 대상도 같은 사용자 데이터로 제한합니다.
    item = db.scalar(
        select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.owner_id == owner_id)
    )
    # 없는 항목을 삭제해도 성공으로 오인하지 않도록 404를 반환합니다.
    if item is None:
        raise ApiError("WARDROBE_NOT_FOUND", "옷장 항목을 찾을 수 없습니다.", 404)
    # 세션에서 삭제 대상으로 표시합니다.
    db.delete(item)
    # 삭제를 확정합니다.
    db.commit()
    # 앱이 어떤 항목이 지워졌는지 확인할 수 있게 ID를 돌려줍니다.
    return DeleteResponse(id=item_id, deleted=True)
