"""검증 시드의 입력 검증·멱등성·원자성을 확인합니다."""

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.db.models import (
    MachineCourse,
    MachineCourseSetting,
    MachineModel,
    Product,
    ProductCareInstruction,
)
from backend.seed.load_verified import load_seed_data
from backend.seed.washwise_demo import verified_seed


def full_seed() -> dict:
    """제품과 기기 하위 구조를 모두 포함한 테스트 입력입니다."""

    return {
        "products": [
            {
                "product_key": "test/product-1",
                "brand": "테스트 브랜드",
                "product_name": "테스트 제품",
                "source_type": "official_product_information",
                "verification_status": "unconfirmed",
                "care_instructions": [
                    {
                        "field_name": "wash_temperature_celsius",
                        "value_text": "30",
                        "source_type": "official_product_information",
                        "verification_status": "unconfirmed",
                    }
                ],
            }
        ],
        "machine_models": [
            {
                "machine_key": "test/machine-1",
                "machine_type": "washer",
                "manufacturer": "테스트 제조사",
                "model_name": "테스트 모델",
                "source_url": "https://example.test/machine-1",
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
                            }
                        ],
                    }
                ],
            }
        ],
    }


def count_rows(db_session, model) -> int:
    """모델별 저장 건수를 반환합니다."""

    return db_session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_loader_is_idempotent(db_session):
    """같은 시드를 두 번 넣어도 행 수가 늘지 않는지 확인합니다."""

    # 첫 번째 적재가 정상적으로 완료됩니다.
    first_result = load_seed_data(db_session, full_seed())
    # 같은 입력을 두 번째로 적재합니다.
    second_result = load_seed_data(db_session, full_seed())
    # 두 실행 모두 같은 논리 데이터 개수를 보고해야 합니다.
    assert first_result == second_result
    # 각 안정 키 레코드가 정확히 한 건만 존재해야 합니다.
    assert count_rows(db_session, Product) == 1
    assert count_rows(db_session, ProductCareInstruction) == 1
    assert count_rows(db_session, MachineModel) == 1
    assert count_rows(db_session, MachineCourse) == 1
    assert count_rows(db_session, MachineCourseSetting) == 1


def test_invalid_seed_is_rejected_before_writes(db_session):
    """중복된 제품 필드가 저장 전에 거부되는지 확인합니다."""

    # 유일해야 하는 care field를 두 번 넣은 잘못된 입력입니다.
    invalid_seed = full_seed()
    invalid_seed["products"][0]["care_instructions"].append(
        {
            "field_name": "wash_temperature_celsius",
            "value_text": "40",
            "source_type": "official_product_information",
            "verification_status": "unconfirmed",
        }
    )
    # Pydantic 검증 단계에서 실패해야 합니다.
    with pytest.raises(ValidationError):
        load_seed_data(db_session, invalid_seed)
    # 검증 실패 후에는 제품·기기 어느 것도 부분 저장되지 않습니다.
    assert count_rows(db_session, Product) == 0
    assert count_rows(db_session, MachineModel) == 0


def test_official_named_settings_keep_stable_keys(db_session):
    """공식 LG 이름형 설정을 두 번 넣어도 새 설정 조합이 생기지 않습니다."""

    seed = verified_seed()
    load_seed_data(db_session, seed)
    first_keys = set(db_session.scalars(select(MachineCourseSetting.setting_key)).all())
    load_seed_data(db_session, seed)
    second_keys = set(db_session.scalars(select(MachineCourseSetting.setting_key)).all())

    # 공식 파일의 3개 코스별 기본 조합만 남고 섭씨·RPM 추정 조합은 생기지 않습니다.
    assert count_rows(db_session, MachineCourseSetting) == 3
    assert first_keys == second_keys
    assert all("Warm" in key or "Cold" in key or "Hot" in key for key in second_keys)
