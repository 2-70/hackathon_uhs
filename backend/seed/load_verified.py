"""제품·기기 검증 시드를 원자적으로 멱등성 있게 적재합니다."""

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    MachineCourse,
    MachineCourseSetting,
    MachineModel,
    Product,
    ProductCareInstruction,
)
from backend.app.db.session import SessionLocal


class CareInstructionSeed(BaseModel):
    """제품 한 필드의 검증된 관리 정보입니다."""

    model_config = ConfigDict(extra="forbid")
    field_name: str = Field(min_length=1, max_length=100)
    value_text: str = Field(min_length=1, max_length=200)
    evidence: str | None = Field(default=None, max_length=300)
    source_type: str = Field(min_length=1, max_length=50)
    source_url: str | None = Field(default=None, max_length=500)
    verification_status: str = Field(min_length=1, max_length=30)


class ProductSeed(BaseModel):
    """공식 제품과 하위 관리 정보의 입력 구조입니다."""

    model_config = ConfigDict(extra="forbid")
    product_key: str = Field(min_length=1, max_length=160)
    brand: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=200)
    official_url: str | None = Field(default=None, max_length=500)
    catalog_details: dict[str, Any] | None = None
    source_type: str = Field(min_length=1, max_length=50)
    verification_status: str = Field(min_length=1, max_length=30)
    care_instructions: list[CareInstructionSeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_care_fields(self) -> "ProductSeed":
        """한 제품 안에서 같은 관리 필드가 두 번 오지 않게 검증합니다."""

        # DB 유일성 제약에 의존하기 전에 입력 자체를 명확한 오류로 거부합니다.
        field_names = [item.field_name for item in self.care_instructions]
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"제품 {self.product_key}의 care_instructions 필드가 중복되었습니다.")
        return self


class SettingSeed(BaseModel):
    """코스에서 실제로 확인된 설정 조합입니다."""

    model_config = ConfigDict(extra="forbid")
    temperature_celsius: int | None = Field(default=None, ge=0, le=100)
    temperature_setting: str | None = Field(default=None, max_length=40)
    wash_strength: str | None = Field(default=None, max_length=30)
    spin_level: str | None = Field(default=None, max_length=40)
    spin_rpm: int | None = Field(default=None, ge=0)
    water_level: str | None = Field(default=None, max_length=40)
    dry_level: str | None = Field(default=None, max_length=40)
    duration_minutes: int | None = Field(default=None, ge=0)
    source_url: str | None = Field(default=None, max_length=500)
    verification_status: str = Field(min_length=1, max_length=30)
    is_default: bool = False
    manual_page: int | None = Field(default=None, ge=1)
    evidence: str | None = Field(default=None, max_length=500)

    @property
    def setting_key(self) -> str:
        """nullable 필드를 포함해 같은 조합을 찾을 수 있는 키를 만듭니다."""

        # 각 값 사이에 구분자를 넣어 30·약과 3·0약 같은 충돌을 피합니다.
        values = (
            self.temperature_celsius,
            self.spin_level,
            self.water_level,
            self.dry_level,
            self.duration_minutes,
        )
        # None도 문자열로 명시해 비어 있는 값의 위치를 보존합니다.
        key = "|".join("null" if value is None else str(value) for value in values)
        # 새 공식 시드만 이름 온도와 RPM을 키 뒤에 추가해 구형 키를 바꾸지 않습니다.
        if self.temperature_setting is not None or self.spin_rpm is not None:
            extra_values = [self.temperature_setting, self.spin_rpm]
            # 기존 AI 공식 시드는 두 값으로 만든 키를 유지하고, 새 강도 값이 있을 때만 확장합니다.
            if self.wash_strength is not None:
                extra_values.append(self.wash_strength)
            key += "|" + json.dumps(extra_values, ensure_ascii=False)
        elif self.wash_strength is not None:
            # 숫자 온도·RPM만 있던 구형 키도 새 강도가 제공되지 않으면 그대로 유지됩니다.
            key += "|" + json.dumps([None, None, self.wash_strength], ensure_ascii=False)
        return key


class CourseSeed(BaseModel):
    """기기 모델의 코스와 확인된 조합 목록입니다."""

    model_config = ConfigDict(extra="forbid")
    course_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    settings: list[SettingSeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_settings(self) -> "CourseSeed":
        """같은 코스의 동일 설정 조합을 중복 저장하지 않게 합니다."""

        # 정규화 키가 중복되면 실제로 확인되지 않은 새 조합이 생긴 것처럼 보일 수 있습니다.
        setting_keys = [item.setting_key for item in self.settings]
        if len(setting_keys) != len(set(setting_keys)):
            raise ValueError(f"코스 {self.course_key}의 settings 조합이 중복되었습니다.")
        return self


class MachineModelSeed(BaseModel):
    """공식 기기 모델과 코스의 입력 구조입니다."""

    model_config = ConfigDict(extra="forbid")
    machine_key: str = Field(min_length=1, max_length=160)
    machine_type: str = Field(min_length=1, max_length=40)
    manufacturer: str = Field(min_length=1, max_length=120)
    model_name: str = Field(min_length=1, max_length=160)
    source_url: str | None = Field(default=None, max_length=500)
    verification_status: str = Field(min_length=1, max_length=30)
    verified_scope: str | None = Field(default=None, max_length=500)
    capacity_kg: float | None = Field(default=None, gt=0)
    release_year: int | None = Field(default=None, ge=1900, le=2100)
    capacity_source_url: str | None = Field(default=None, max_length=500)
    capacity_verification_status: str | None = Field(default=None, max_length=30)
    courses: list[CourseSeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_courses(self) -> "MachineModelSeed":
        """한 모델 안의 코스 키 중복을 사전에 검증합니다."""

        # 코스 키는 모델 내부에서만 고유하면 되므로 이 모델의 목록에서만 비교합니다.
        course_keys = [course.course_key for course in self.courses]
        if len(course_keys) != len(set(course_keys)):
            raise ValueError(f"기기 모델 {self.machine_key}의 course_key가 중복되었습니다.")
        return self


class SeedDocument(BaseModel):
    """제품과 기기 데이터를 함께 담는 시드 문서입니다."""

    model_config = ConfigDict(extra="forbid")
    products: list[ProductSeed] = Field(default_factory=list)
    machine_models: list[MachineModelSeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_top_level_keys(self) -> "SeedDocument":
        """시드 한 파일 안에서 안정적인 키가 중복되지 않는지 확인합니다."""

        # 같은 product_key가 두 번 나오면 어느 값이 정답인지 모호해집니다.
        product_keys = [product.product_key for product in self.products]
        # 같은 machine_key도 동일한 이유로 한 번만 허용합니다.
        machine_keys = [machine.machine_key for machine in self.machine_models]
        # 중복을 쓰기 전에 거부해 부분 저장 가능성을 줄입니다.
        if len(product_keys) != len(set(product_keys)):
            raise ValueError("시드의 product_key가 중복되었습니다.")
        if len(machine_keys) != len(set(machine_keys)):
            raise ValueError("시드의 machine_key가 중복되었습니다.")
        return self


def _upsert_product(db: Session, seed: ProductSeed) -> Product:
    """product_key 기준으로 제품과 관리 정보를 추가하거나 갱신합니다."""

    # 안정 키로 기존 제품을 찾으면 반복 실행에도 새 ID를 만들지 않습니다.
    product = db.scalar(select(Product).where(Product.product_key == seed.product_key))
    # 처음 보는 제품이면 새 레코드를 세션에 추가합니다.
    if product is None:
        product = Product(product_key=seed.product_key)
        db.add(product)
    # 기존·신규 모두 시드의 확인된 최신 메타데이터로 맞춥니다.
    product.brand = seed.brand
    product.product_name = seed.product_name
    product.official_url = seed.official_url
    product.catalog_details = seed.catalog_details
    product.source_type = seed.source_type
    product.verification_status = seed.verification_status
    # 부모 ID가 필요하므로 flush 후 하위 지침을 처리합니다.
    db.flush()
    for instruction_seed in seed.care_instructions:
        # 제품과 필드 조합을 유일 키로 사용합니다.
        instruction = db.scalar(
            select(ProductCareInstruction).where(
                ProductCareInstruction.product_id == product.id,
                ProductCareInstruction.field_name == instruction_seed.field_name,
            )
        )
        # 새 필드이면 제품에 연결한 하위 레코드를 생성합니다.
        if instruction is None:
            instruction = ProductCareInstruction(
                product_id=product.id,
                field_name=instruction_seed.field_name,
            )
            db.add(instruction)
        # 같은 필드가 이미 있어도 출처와 확인 상태는 최신 입력으로 갱신합니다.
        instruction.value_text = instruction_seed.value_text
        instruction.evidence = instruction_seed.evidence
        instruction.source_type = instruction_seed.source_type
        instruction.source_url = instruction_seed.source_url
        instruction.verification_status = instruction_seed.verification_status
    return product


def upsert_machine_model(db: Session, seed: MachineModelSeed) -> MachineModel:
    """machine_key 기준으로 모델·코스·설정 조합을 추가하거나 갱신합니다."""

    # 안정 키가 같은 모델은 기존 ID를 유지해 사용자 등록 참조를 보존합니다.
    machine = db.scalar(select(MachineModel).where(MachineModel.machine_key == seed.machine_key))
    # 신규 모델은 우선 부모 레코드만 만듭니다.
    if machine is None:
        machine = MachineModel(machine_key=seed.machine_key)
        db.add(machine)
    # 모델의 기본 정보와 공식 확인 범위를 갱신합니다.
    machine.machine_type = seed.machine_type
    machine.manufacturer = seed.manufacturer
    machine.model_name = seed.model_name
    machine.source_url = seed.source_url
    machine.verification_status = seed.verification_status
    machine.verified_scope = seed.verified_scope
    machine.capacity_kg = seed.capacity_kg
    machine.release_year = seed.release_year
    machine.capacity_source_url = seed.capacity_source_url
    machine.capacity_verification_status = seed.capacity_verification_status
    # 모델 ID가 있어야 코스의 외래 키를 채울 수 있습니다.
    db.flush()
    for course_seed in seed.courses:
        # 모델과 코스 키 조합으로 같은 코스를 재사용합니다.
        course = db.scalar(
            select(MachineCourse).where(
                MachineCourse.machine_model_id == machine.id,
                MachineCourse.course_key == course_seed.course_key,
            )
        )
        # 신규 코스는 부모 모델 ID를 함께 저장합니다.
        if course is None:
            course = MachineCourse(
                machine_model_id=machine.id,
                course_key=course_seed.course_key,
            )
            db.add(course)
        # 코스 표시 정보는 시드 값으로 갱신합니다.
        course.name = course_seed.name
        course.description = course_seed.description
        # 설정 외래 키를 위해 코스 ID를 먼저 생성합니다.
        db.flush()
        for setting_seed in course_seed.settings:
            # 코스와 정규화 설정 키 조합으로 중복을 차단합니다.
            setting = db.scalar(
                select(MachineCourseSetting).where(
                    MachineCourseSetting.course_id == course.id,
                    MachineCourseSetting.setting_key == setting_seed.setting_key,
                )
            )
            # 신규 조합은 코스에 연결해 저장합니다.
            if setting is None:
                setting = MachineCourseSetting(
                    course_id=course.id,
                    setting_key=setting_seed.setting_key,
                )
                db.add(setting)
            # 확인된 조합의 각 값을 그대로 저장하며 없는 조합을 추측해 만들지 않습니다.
            setting.temperature_celsius = setting_seed.temperature_celsius
            setting.temperature_setting = setting_seed.temperature_setting
            setting.wash_strength = setting_seed.wash_strength
            setting.spin_level = setting_seed.spin_level
            setting.spin_rpm = setting_seed.spin_rpm
            setting.water_level = setting_seed.water_level
            setting.dry_level = setting_seed.dry_level
            setting.duration_minutes = setting_seed.duration_minutes
            setting.source_url = setting_seed.source_url
            setting.verification_status = setting_seed.verification_status
            setting.is_default = setting_seed.is_default
            setting.manual_page = setting_seed.manual_page
            setting.evidence = setting_seed.evidence
    return machine


def load_seed_data(db: Session, raw_data: dict[str, Any]) -> dict[str, int]:
    """시드 전체를 검증하고 하나의 트랜잭션으로 멱등성 있게 저장합니다."""

    # 모든 필드와 중복 키를 먼저 검증해 쓰기 도중 입력 오류가 생기지 않게 합니다.
    document = SeedDocument.model_validate(raw_data)
    try:
        # 제품과 기기 쓰기를 같은 트랜잭션에 넣어 일부만 반영되지 않게 합니다.
        for product_seed in document.products:
            _upsert_product(db, product_seed)
        for machine_seed in document.machine_models:
            upsert_machine_model(db, machine_seed)
        # 모든 레코드가 정상적으로 처리된 뒤에만 커밋합니다.
        db.commit()
    except Exception:
        # DB 오류가 나면 제품·기기 변경을 모두 취소합니다.
        db.rollback()
        raise
    # 로더 실행 결과를 로그나 CLI에서 사람이 확인할 수 있게 반환합니다.
    return {
        "products": len(document.products),
        "machine_models": len(document.machine_models),
        "courses": sum(len(machine.courses) for machine in document.machine_models),
        "settings": sum(
            len(course.settings)
            for machine in document.machine_models
            for course in machine.courses
        ),
    }


def load_seed_file(db: Session, path: Path) -> dict[str, int]:
    """JSON 파일을 읽어 시드 로더에 전달합니다."""

    # UTF-8 JSON을 사용해 한글 제품명과 출처를 보존합니다.
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    # 파일 읽기와 데이터 저장을 분리해 테스트에서 딕셔너리를 직접 주입할 수 있게 합니다.
    return load_seed_data(db, raw_data)


def main() -> int:
    """`python -m backend.seed.load_verified --file ...` CLI 진입점입니다."""

    # 실행 파일 경로를 명시적으로 받도록 해 어떤 시드를 넣는지 확인 가능하게 합니다.
    parser = argparse.ArgumentParser(description="WashWise 검증 시드 로더")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="시드 JSON 파일 경로")
    source.add_argument("--washwise-demo", action="store_true", help="WashWise 검증 상품과 기기 적재")
    args = parser.parse_args()
    try:
        # 하나의 세션에서 전체 파일을 처리합니다.
        with SessionLocal() as db:
            if args.washwise_demo:
                from backend.seed.washwise_demo import verified_seed

                result = load_seed_data(db, verified_seed())
            else:
                result = load_seed_file(db, args.file)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        # 입력 파일 오류는 사용자에게 보여주되 비밀정보를 출력하지 않습니다.
        print(f"시드 입력 오류: {exc}")
        return 2
    except SQLAlchemyError as exc:
        # DB 오류는 상세 traceback 대신 실패 사실만 CLI에 보여줍니다.
        print(f"시드 저장 실패: {type(exc).__name__}")
        return 1
    # 성공한 개수를 JSON으로 출력해 반복 실행 결과를 비교할 수 있게 합니다.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
