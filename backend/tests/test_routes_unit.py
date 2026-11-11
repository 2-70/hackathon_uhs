"""이벤트 루프 없이 라우터의 DB 로직을 직접 검증합니다."""

from sqlalchemy import select

from backend.app.api.routes.machines import list_machine_courses, list_machine_models
from backend.app.api.routes.user_machines import create_user_machine, list_user_machines
from backend.app.api.routes.wardrobe import (
    create_wardrobe_item,
    delete_wardrobe_item,
    list_wardrobe_items,
    update_wardrobe_item,
)
from backend.app.api.schemas import (
    UserMachineCreate,
    UserMachineRead,
    WardrobeCreate,
    WardrobeRead,
    WardrobeUpdate,
)
from backend.app.db.models import MachineModel
from backend.seed.load_verified import load_seed_data


def machine_seed() -> dict:
    """라우터 검증에 사용할 비공식 테스트 데이터입니다."""

    # 실제 공식 데이터와 혼동하지 않도록 test 키와 unconfirmed 상태를 사용합니다.
    return {
        "products": [],
        "machine_models": [
            {
                "machine_key": "unit-test/machine",
                "machine_type": "washer",
                "manufacturer": "테스트 제조사",
                "model_name": "단위 테스트 세탁기",
                "verification_status": "unconfirmed",
                "courses": [
                    {
                        "course_key": "normal",
                        "name": "표준",
                        "settings": [
                            {
                                "temperature_celsius": 30,
                                "spin_level": "low",
                                "verification_status": "unconfirmed",
                            },
                            {
                                "temperature_celsius": 40,
                                "spin_level": "medium",
                                "verification_status": "unconfirmed",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_wardrobe_route_functions_crud(db_session):
    """옷장 라우터의 등록·조회·수정·삭제를 직접 검증합니다."""

    # 실제 API와 같은 Pydantic 요청 객체를 만들어 등록 함수에 전달합니다.
    created = create_wardrobe_item(
        WardrobeCreate(item_name="단위 테스트 셔츠", care_temperature_celsius=30),
        db_session,
        "demo-user",
    )
    # 서버가 ID와 고정 데모 소유자를 저장했는지 확인합니다.
    assert created.id
    assert created.owner_id == "demo-user"
    # FastAPI 응답 모델로도 변환되어 HTTP 직렬화에 필요한 필드가 모두 있는지 확인합니다.
    assert WardrobeRead.model_validate(created).item_name == "단위 테스트 셔츠"

    # 별도 목록 호출에서 저장된 레코드가 다시 보이는지 확인합니다.
    listed = list_wardrobe_items(db_session, "demo-user")
    assert len(listed) == 1
    assert listed[0].item_name == "단위 테스트 셔츠"

    # PATCH와 같은 부분 수정이 기존 이름을 유지하면서 색상만 바꾸는지 확인합니다.
    updated = update_wardrobe_item(
        created.id,
        WardrobeUpdate(color="white"),
        db_session,
        "demo-user",
    )
    assert updated.color == "white"
    assert updated.item_name == "단위 테스트 셔츠"

    # 삭제 결과와 삭제 후 빈 목록을 확인합니다.
    deleted = delete_wardrobe_item(created.id, db_session, "demo-user")
    assert deleted.deleted is True
    assert list_wardrobe_items(db_session, "demo-user") == []


def test_machine_and_user_machine_route_functions(db_session):
    """공용 코스 조합과 사용자 기기 복원 로직을 직접 검증합니다."""

    # 공용 모델·코스·설정 조합을 테스트 DB에 적재합니다.
    load_seed_data(db_session, machine_seed())
    # 검색 API 로직이 공용 모델을 반환하는지 확인합니다.
    models = list_machine_models(db_session, query="단위", machine_type="washer")
    assert len(models) == 1
    machine = models[0]

    # 코스 조회가 입력에 존재한 두 조합만 반환하는지 확인합니다.
    courses_response = list_machine_courses(machine.id, db_session)
    assert len(courses_response.courses) == 1
    assert len(courses_response.courses[0].settings) == 2
    assert {
        setting.temperature_celsius for setting in courses_response.courses[0].settings
    } == {30, 40}

    # 공용 모델을 참조하는 사용자 기기를 등록합니다.
    registered = create_user_machine(
        UserMachineCreate(
            machine_type="washer",
            display_name="우리집 세탁기",
            machine_model_id=machine.id,
        ),
        db_session,
        "demo-user",
    )
    assert registered.machine_model_id == machine.id
    # 중첩된 공용 모델을 포함한 응답 스키마 검증도 통과해야 합니다.
    assert UserMachineRead.model_validate(registered).machine_model is not None

    # 수동 입력이 공용 모델 필드가 아닌 사용자 등록 레코드에만 저장되는지 확인합니다.
    manual = create_user_machine(
        UserMachineCreate(
            machine_type="washer",
            display_name="수동 세탁기",
            manual_input={"manufacturer": "알 수 없음"},
        ),
        db_session,
        "demo-user",
    )
    assert manual.machine_model_id is None
    assert manual.manual_input == {"manufacturer": "알 수 없음"}

    # 재조회 함수가 같은 소유자의 두 등록을 모두 복원하는지 확인합니다.
    restored = list_user_machines(db_session, "demo-user")
    assert {item.display_name for item in restored} == {"우리집 세탁기", "수동 세탁기"}
    # 수동 입력 등록이 공용 모델의 이름을 덮어쓰지 않았는지 DB에서 재확인합니다.
    stored_model = db_session.scalar(select(MachineModel).where(MachineModel.id == machine.id))
    assert stored_model is not None
    assert stored_model.model_name == "단위 테스트 세탁기"
