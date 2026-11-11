"""세탁 계획·설정검증의 안전 분류, 최적화, 최신 입력 계약을 검증합니다."""

from backend.app.db.models import (
    MachineCourse,
    MachineCourseSetting,
    MachineModel,
    UserMachine,
    WardrobeCareField,
    WardrobeItem,
)
from backend.app.planning.engine import GroupChoice, MachineSettingValue, minimize_groups


def _create_machine(
    db_session,
    *,
    temperature_celsius=30,
    temperature_setting=None,
    wash_strength="gentle",
    spin_rpm=800,
    spin_level="low",
    capacity_kg=8.0,
):
    """계획 테스트에 사용할 confirmed 모델·코스·설정을 만듭니다."""

    model = MachineModel(
        machine_key=(
            f"test/machine/{temperature_celsius}/{temperature_setting}/{spin_rpm}/{capacity_kg}"
        ),
        machine_type="washer",
        manufacturer="테스트 제조사",
        model_name="계획 테스트 세탁기",
        verification_status="confirmed",
        capacity_kg=capacity_kg,
        capacity_verification_status="confirmed" if capacity_kg is not None else None,
    )
    course = MachineCourse(course_key="gentle", name="섬세", machine_model=model)
    setting = MachineCourseSetting(
        setting_key="setting-1",
        temperature_celsius=temperature_celsius,
        temperature_setting=temperature_setting,
        wash_strength=wash_strength,
        spin_rpm=spin_rpm,
        spin_level=spin_level,
        is_default=True,
        verification_status="confirmed",
        course=course,
    )
    db_session.add_all([model, course, setting])
    db_session.flush()
    user_machine = UserMachine(
        owner_id="demo-user",
        machine_type="washer",
        display_name="테스트 기기",
        machine_model=model,
    )
    db_session.add(user_machine)
    db_session.commit()
    return user_machine, setting


def _create_item(
    db_session,
    name,
    *,
    owner_id="demo-user",
    wash_method="machine_wash",
    temperature=30,
    strength="gentle",
    max_spin_rpm=800,
    color_family="light",
    color_bleed_risk=False,
    wash_separately=False,
    weight_grams=500,
):
    """핵심 조건이 모두 confirmed인 의류를 만듭니다."""

    item = WardrobeItem(
        owner_id=owner_id,
        item_name=name,
        care_wash_method=wash_method,
        care_temperature_celsius=temperature,
        care_wash_strength=strength,
        care_gentle=strength != "normal",
        care_max_spin_rpm=max_spin_rpm,
        color_family=color_family,
        color_bleed_risk=color_bleed_risk,
        wash_separately=wash_separately,
        weight_grams=weight_grams,
        care_tumble_dry_allowed=False,
        care_natural_dry="line_dry",
        source_type="physical_label",
        verification_status="confirmed",
        source_reference="label:test",
    )
    db_session.add(item)
    db_session.commit()
    return item


def _plan_payload(machine_id, item_ids, **overrides):
    """반복되는 계획 요청의 최신 입력 식별값을 포함합니다."""

    payload = {
        "request_id": "plan-test-1",
        "input_version": 1,
        "wardrobe_item_ids": item_ids,
        "user_machine_id": machine_id,
    }
    payload.update(overrides)
    return payload


def test_wardrobe_rejects_scalar_and_care_field_mismatch(client):
    """같은 요청 안의 서로 다른 표현은 CONFLICTING_INPUT으로 거부합니다."""

    response = client.post(
        "/api/wardrobe",
        json={
            "item_name": "충돌 셔츠",
            "care_temperature_celsius": 30,
            "care_fields": [
                {
                    "field_name": "care_temperature_celsius",
                    "value": 40,
                    "knowledge_status": "confirmed",
                }
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CONFLICTING_INPUT"


def test_plan_minimizes_groups_and_is_order_independent(client, db_session):
    """같이 세탁 가능한 옷은 한 그룹이며 요청 순서를 바꿔도 결과가 같습니다."""

    machine, _ = _create_machine(db_session)
    first = _create_item(db_session, "첫 번째 셔츠")
    second = _create_item(db_session, "두 번째 셔츠")

    normal = client.post(
        "/api/plans", json=_plan_payload(machine.id, [first.id, second.id])
    )
    reversed_order = client.post(
        "/api/plans",
        json=_plan_payload(machine.id, [second.id, first.id], request_id="plan-test-2"),
    )
    assert normal.status_code == 200
    assert normal.json()["machine_wash_count"] == 1
    assert normal.json()["assignment_invariant"]["valid"] is True
    assert normal.json()["groups"] == reversed_order.json()["groups"]


def test_plan_separates_light_dark_and_separate_wash(client, db_session):
    """밝은색·어두운색 및 단독세탁 조건은 같은 그룹에 넣지 않습니다."""

    machine, _ = _create_machine(db_session)
    light = _create_item(db_session, "흰 셔츠", color_family="light")
    dark = _create_item(db_session, "검은 셔츠", color_family="dark")
    separate = _create_item(db_session, "단독 세탁", wash_separately=True)

    response = client.post(
        "/api/plans", json=_plan_payload(machine.id, [light.id, dark.id, separate.id])
    )
    assert response.status_code == 200
    assert response.json()["machine_wash_count"] == 3


def test_plan_classification_priority_and_conflict(client, db_session):
    """금지·손세탁을 먼저 분류하고 실제 출처 충돌은 보류로 반환합니다."""

    machine, _ = _create_machine(db_session)
    prohibited = _create_item(db_session, "물세탁 금지", wash_method="do_not_wash")
    hand = _create_item(db_session, "손세탁", wash_method="hand_wash")
    conflict = _create_item(db_session, "충돌 의류")
    conflict.care_fields.append(
        WardrobeCareField(
            field_name="care_temperature_celsius",
            value_json=30,
            source_type="physical_label",
            knowledge_status="conflict",
            conflicting_values=[
                {"value": 30, "source_type": "physical_label"},
                {"value": 40, "source_type": "official_product_information"},
            ],
        )
    )
    db_session.commit()

    response = client.post(
        "/api/plans",
        json=_plan_payload(machine.id, [prohibited.id, hand.id, conflict.id]),
    )
    body = response.json()
    assert response.status_code == 200
    assert [item["wardrobe_item_id"] for item in body["machine_wash_prohibited_items"]] == [
        prohibited.id
    ]
    assert [item["wardrobe_item_id"] for item in body["hand_wash_items"]] == [hand.id]
    assert body["pending_confirmation_items"][0]["wardrobe_item_id"] == conflict.id


def test_named_only_setting_is_pending_not_unsupported(client, db_session):
    """Cold·Low 이름을 임의 수치로 바꾸지 않고 비교 불가로 보류합니다."""

    machine, _ = _create_machine(
        db_session,
        temperature_celsius=None,
        temperature_setting="Cold",
        spin_rpm=None,
        spin_level="Low",
    )
    item = _create_item(db_session, "숫자 제한 의류")
    response = client.post("/api/plans", json=_plan_payload(machine.id, [item.id]))
    body = response.json()
    assert response.status_code == 200
    assert body["unsupported_items"] == []
    assert body["pending_confirmation_items"][0]["wardrobe_item_id"] == item.id


def test_comparable_but_impossible_setting_is_unsupported(client, db_session):
    """모든 비교가 가능하고 조건을 위반할 때만 미지원으로 분류합니다."""

    machine, _ = _create_machine(
        db_session,
        temperature_celsius=60,
        wash_strength="normal",
        spin_rpm=1200,
    )
    item = _create_item(db_session, "섬세 의류", temperature=30, strength="gentle")
    response = client.post("/api/plans", json=_plan_payload(machine.id, [item.id]))
    assert response.status_code == 200
    assert response.json()["unsupported_items"][0]["wardrobe_item_id"] == item.id


def test_capacity_exceeded_and_not_verified(client, db_session):
    """확인된 용량 초과는 미지원, 용량 미확인은 계획 가능하되 not_verified입니다."""

    small_machine, _ = _create_machine(db_session, capacity_kg=5.0)
    heavy = _create_item(db_session, "무거운 이불", weight_grams=6000)
    exceeded = client.post(
        "/api/plans", json=_plan_payload(small_machine.id, [heavy.id])
    )
    assert exceeded.json()["unsupported_items"][0]["wardrobe_item_id"] == heavy.id

    unknown_machine, _ = _create_machine(db_session, capacity_kg=None)
    normal = _create_item(db_session, "보통 셔츠")
    unknown = client.post(
        "/api/plans", json=_plan_payload(unknown_machine.id, [normal.id])
    )
    assert unknown.status_code == 200
    assert unknown.json()["capacity_status"] == "not_verified"


def test_plan_rejects_size_duplicate_foreign_and_stale_inputs(client, db_session):
    """요청 크기·중복·소유권·예상 버전 오류를 각각 거부합니다."""

    machine, _ = _create_machine(db_session)
    item = _create_item(db_session, "정상 의류")
    duplicate = client.post(
        "/api/plans", json=_plan_payload(machine.id, [item.id, item.id])
    )
    assert duplicate.status_code == 422

    too_many = client.post(
        "/api/plans", json=_plan_payload(machine.id, [str(index) for index in range(11)])
    )
    assert too_many.status_code == 422

    foreign = _create_item(db_session, "타인 의류", owner_id="another-user")
    foreign_response = client.post(
        "/api/plans", json=_plan_payload(machine.id, [foreign.id])
    )
    assert foreign_response.status_code == 404
    assert foreign_response.json()["error"]["code"] == "WARDROBE_NOT_OWNED"

    stale = client.post(
        "/api/plans",
        json=_plan_payload(
            machine.id,
            [item.id],
            expected_item_versions={item.id: "2000-01-01T00:00:00+00:00"},
        ),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_INPUT"


def test_settings_validation_status_priority_and_alternatives(client, db_session):
    """적합·위반·부분입력을 판정하고 실제 가능한 대체 조합만 반환합니다."""

    machine, setting = _create_machine(db_session)
    # 기본 추천과 다른 더 약한 조합도 실제 지원 조합이면 suitable이어야 합니다.
    alternate = MachineCourseSetting(
        course_id=setting.course_id,
        setting_key="setting-2",
        temperature_celsius=20,
        wash_strength="very_gentle",
        spin_rpm=400,
        spin_level="very-low",
        is_default=False,
        verification_status="confirmed",
    )
    db_session.add(alternate)
    db_session.commit()
    # 테스트 fixture는 같은 세션을 재사용하므로 관계 캐시를 비워 실제 새 요청처럼 다시 읽습니다.
    db_session.expire_all()
    item = _create_item(db_session, "검증 셔츠")
    base = {
        "request_id": "validate-1",
        "input_version": 2,
        "wardrobe_item_ids": [item.id],
        "user_machine_id": machine.id,
    }
    suitable = client.post(
        "/api/settings/validate", json={**base, "setting_id": setting.id}
    )
    assert suitable.status_code == 200
    assert suitable.json()["status"] == "suitable"
    assert suitable.json()["alternatives"]

    different_but_safe = client.post(
        "/api/settings/validate",
        json={**base, "request_id": "validate-safe-2", "setting_id": alternate.id},
    )
    assert different_but_safe.status_code == 200, different_but_safe.json()
    assert different_but_safe.json()["status"] == "suitable"

    violation = client.post(
        "/api/settings/validate",
        json={
            **base,
            "request_id": "validate-2",
            "actual_setting": {
                "temperature_celsius": 60,
                "wash_strength": "normal",
                "spin_rpm": 1200,
            },
        },
    )
    assert violation.json()["status"] == "needs_change"
    assert violation.json()["violations"]

    partial = client.post(
        "/api/settings/validate",
        json={
            **base,
            "request_id": "validate-3",
            "actual_setting": {"temperature_celsius": 30},
        },
    )
    assert partial.json()["status"] == "unknown"
    assert "actual_setting" in partial.json()["unknown_fields"]


def test_subset_dp_beats_largest_first_greedy_counterexample():
    """큰 그룹부터 고르는 탐욕법의 3회보다 DP가 2회 해를 찾습니다."""

    setting = MachineSettingValue(
        course_id="course",
        course_key="course",
        course_name="코스",
        setting_id="setting",
        setting_key="setting",
        temperature_celsius=30,
        temperature_setting=None,
        wash_strength="gentle",
        spin_rpm=800,
        spin_level="low",
        water_level=None,
        dry_level=None,
        is_default=True,
        verification_status="confirmed",
    )
    items = [object() for _ in range(6)]
    choices = [
        GroupChoice(0b001111, ("0", "1", "2", "3"), setting, "verified", 1000),
        GroupChoice(0b010011, ("0", "1", "4"), setting, "verified", 900),
        GroupChoice(0b101100, ("2", "3", "5"), setting, "verified", 900),
    ]
    for index in range(6):
        choices.append(
            GroupChoice(1 << index, (str(index),), setting, "verified", 300)
        )
    result = minimize_groups(items, choices)
    assert len(result) == 2
    assert {choice.mask for choice in result} == {0b010011, 0b101100}
