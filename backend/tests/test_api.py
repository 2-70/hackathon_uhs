"""핵심 API 흐름을 HTTP 수준에서 검증합니다."""

from base64 import b64encode
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from backend.app.db.models import MachineModel, WardrobeItem
from backend.seed.load_verified import load_seed_data


def sample_seed() -> dict:
    """공식 시드가 아닌 테스트 전용 데이터입니다."""

    return {
        "products": [],
        "machine_models": [
            {
                "machine_key": "test-maker/test-washer",
                "machine_type": "washer",
                "manufacturer": "테스트 제조사",
                "model_name": "테스트 세탁기",
                "source_url": "https://example.test/washer",
                "verification_status": "unconfirmed",
                "verified_scope": "자동화 테스트용",
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


def test_health_and_empty_lists(client):
    """서버 상태와 신규 사용자의 빈 목록을 확인합니다."""

    # 마이그레이션된 서버가 살아 있는지 확인합니다.
    assert client.get("/health").json() == {
        "status": "ok",
        "mode": "demo",
        "database": None,
    }
    # 신규 사용자는 빈 옷장 배열을 받아야 합니다.
    assert client.get("/api/wardrobe").json() == []
    # 신규 사용자는 빈 기기 배열을 받아야 합니다.
    assert client.get("/api/user-machines").json() == []


def test_wardrobe_crud_and_owner_filter(client):
    """옷장 등록부터 수정·삭제까지 저장 결과를 확인합니다."""

    # 등록 요청은 필수 이름과 확인되지 않은 사용자 입력 출처를 포함합니다.
    create_response = client.post(
        "/api/wardrobe",
        json={
            "item_name": "흰 셔츠",
            "category": "shirt",
            "care_temperature_celsius": 30,
            "source_type": "user_input",
            "verification_status": "unconfirmed",
        },
    )
    # 등록 성공은 201과 서버 생성 ID를 반환해야 합니다.
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]
    assert create_response.json()["owner_id"] == "demo-user"

    # 새 요청으로 목록을 읽어 DB에 저장된 값이 유지되는지 확인합니다.
    list_response = client.get("/api/wardrobe")
    assert list_response.status_code == 200
    assert list_response.json()[0]["item_name"] == "흰 셔츠"

    # 부분 수정은 전달한 필드만 바꿔야 합니다.
    patch_response = client.patch(f"/api/wardrobe/{item_id}", json={"color": "white"})
    assert patch_response.status_code == 200
    assert patch_response.json()["color"] == "white"
    assert patch_response.json()["item_name"] == "흰 셔츠"

    # 삭제 성공 응답은 삭제된 ID를 알려줍니다.
    delete_response = client.delete(f"/api/wardrobe/{item_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": item_id, "deleted": True}
    # 삭제 후 목록에서 더 이상 항목이 보이지 않습니다.
    assert client.get("/api/wardrobe").json() == []


def test_invalid_wardrobe_input_uses_common_error(client):
    """필수 입력 누락이 공통 오류 계약을 따르는지 확인합니다."""

    # item_name을 빼서 Pydantic 입력 검증을 발생시킵니다.
    response = client.post("/api/wardrobe", json={})
    # 필수 입력 오류는 422여야 합니다.
    assert response.status_code == 422
    # 앱이 분기할 수 있는 안정적인 오류 코드를 확인합니다.
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert response.json()["error"]["details"]["fields"]


def test_wardrobe_photos_are_persisted_and_replaced_atomically(client, db_session):
    def photo(color):
        output = BytesIO()
        Image.new("RGB", (8, 10), color).save(output, "PNG")
        return b64encode(output.getvalue()).decode()

    create = client.post("/api/wardrobe", json={
        "item_name": "흰 셔츠", "photos": {"clothing": photo("white"), "label": photo("blue")},
    })
    assert create.status_code == 201
    path = f"/api/wardrobe/{create.json()['id']}"
    assert create.json()["photo_kinds"] == ["clothing", "label"]
    wardrobe = client.get("/api/wardrobe").json()
    assert wardrobe[0]["photo_kinds"] == ["clothing", "label"]
    assert "photos" not in wardrobe[0]

    clothing = client.get(f"{path}/photos/clothing")
    label = client.get(f"{path}/photos/label")
    assert clothing.headers["content-type"] == label.headers["content-type"] == "image/jpeg"
    assert clothing.content != label.content
    assert Image.open(BytesIO(label.content)).size == (8, 10)

    invalid = client.patch(path, json={"item_name": "변경", "photos": {"label": "invalid"}})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_WARDROBE_PHOTO"
    assert client.get(path).json()["item_name"] == "흰 셔츠"
    assert client.get(f"{path}/photos/label").content == label.content

    updated = client.patch(path, json={"photos": {"label": photo("red")}})
    assert updated.status_code == 200
    assert updated.json()["photo_kinds"] == ["clothing", "label"]
    assert client.get(f"{path}/photos/label").content != label.content
    assert client.get(f"{path}/photos/clothing").content == clothing.content

    other = WardrobeItem(owner_id="another-owner", item_name="다른 옷", clothing_photo=clothing.content)
    db_session.add(other)
    db_session.commit()
    assert client.get(f"/api/wardrobe/{other.id}/photos/clothing").status_code == 404

    assert client.delete(path).status_code == 200
    assert client.get(f"{path}/photos/label").status_code == 404


def test_machine_courses_only_return_verified_combinations(client, db_session):
    """기기 코스 조회가 저장된 조합만 반환하는지 확인합니다."""

    # 테스트용 시드를 저장해 공용 모델과 확인된 조합을 준비합니다.
    load_seed_data(db_session, sample_seed())
    # 시드로 만들어진 모델의 API ID를 조회합니다.
    machine = db_session.scalar(
        select(MachineModel).where(MachineModel.machine_key == "test-maker/test-washer")
    )
    # 모델이 실제로 저장되었음을 확인합니다.
    assert machine is not None

    # 모델의 코스·설정 조회 API를 호출합니다.
    response = client.get(f"/api/machines/{machine.id}/courses")
    assert response.status_code == 200
    # 확인된 두 조합만 존재하고 자동 조합은 만들어지지 않았습니다.
    settings = response.json()["courses"][0]["settings"]
    assert len(settings) == 2
    assert {item["temperature_celsius"] for item in settings} == {30, 40}


def test_user_machine_register_and_restore(client, db_session):
    """공용 모델 참조와 수동 입력을 등록한 뒤 재조회합니다."""

    # 공용 모델 하나를 먼저 준비합니다.
    load_seed_data(db_session, sample_seed())
    machine = db_session.scalar(select(MachineModel))
    assert machine is not None

    # 공용 모델을 참조하는 기기를 등록합니다.
    model_response = client.post(
        "/api/user-machines",
        json={
            "machine_type": "washer",
            "display_name": "우리집 세탁기",
            "machine_model_id": machine.id,
        },
    )
    assert model_response.status_code == 201
    assert model_response.json()["machine_model"]["id"] == machine.id

    # 공용 모델이 없는 수동 입력도 별도 등록으로 보존합니다.
    manual_response = client.post(
        "/api/user-machines",
        json={
            "machine_type": "washer",
            "display_name": "수동 등록 기기",
            "manual_input": {"manufacturer": "알 수 없음", "max_temperature": 40},
        },
    )
    assert manual_response.status_code == 201
    assert manual_response.json()["machine_model_id"] is None

    # 새 GET 요청으로 앱 재실행 시나리오의 복원을 확인합니다.
    restored = client.get("/api/user-machines")
    assert restored.status_code == 200
    assert len(restored.json()) == 2
    assert {item["display_name"] for item in restored.json()} == {
        "우리집 세탁기",
        "수동 등록 기기",
    }
