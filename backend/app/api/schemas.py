"""API 요청과 응답의 자료형을 정의합니다."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceType = Literal[
    "user_input",
    "physical_label",
    "official_product_information",
    "photo_inference",
]
VerificationStatus = Literal["confirmed", "unconfirmed"]
KnowledgeStatus = Literal[
    "confirmed",
    "unconfirmed",
    "needs_confirmation",
    "conflict",
    "not_applicable",
]
CareWashMethod = Literal["machine_wash", "hand_wash", "do_not_wash"]
WashStrength = Literal["normal", "gentle", "very_gentle"]
ColorFamily = Literal["light", "dark", "unknown"]


class ProductReference(BaseModel):
    """옷과 연결된 상품 표시 정보 및 공용 상품 ID입니다."""

    brand: str | None = Field(default=None, max_length=120)
    product_name: str | None = Field(default=None, max_length=200)
    product_code: str | None = Field(default=None, max_length=120)
    matched_product_id: str | None = Field(default=None, max_length=36)
    official_url: str | None = Field(default=None, max_length=500)


class CareConflictValue(BaseModel):
    """서로 다른 출처가 제시한 값과 근거 한 건입니다."""

    value: Any
    source_type: SourceType
    source_reference: str | None = Field(default=None, max_length=500)
    evidence: str | None = Field(default=None, max_length=500)


class CareFieldInput(BaseModel):
    """의류 관리 필드 한 건의 값·출처·확인 상태입니다."""

    field_name: str = Field(min_length=1, max_length=100)
    value: Any | None = None
    source_type: SourceType = "user_input"
    source_reference: str | None = Field(default=None, max_length=500)
    evidence: str | None = Field(default=None, max_length=500)
    knowledge_status: KnowledgeStatus = "unconfirmed"
    conflicting_values: list[CareConflictValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_conflict_evidence(self) -> "CareFieldInput":
        """충돌 상태에는 실제 후보 값이 둘 이상 있어야 합니다."""

        # 충돌이라고만 표시하고 근거를 잃는 저장을 막습니다.
        if self.knowledge_status == "conflict" and len(self.conflicting_values) < 2:
            raise ValueError("conflict 상태에는 conflicting_values가 2개 이상 필요합니다.")
        return self


class CareFieldRead(CareFieldInput):
    """저장된 필드 근거 응답입니다."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: str
    value: Any | None = Field(default=None, validation_alias="value_json")
    updated_at: datetime


class ErrorPayload(BaseModel):
    """모바일이 분기할 수 있는 공통 오류 본문입니다."""

    # 앱 로직이 문구 변경과 무관하게 오류를 처리하도록 코드를 제공합니다.
    code: str
    # 사용자에게 표시할 수 있는 안내 문구입니다.
    message: str
    # 필드 위치나 검증 목록 같은 선택 상세 정보입니다.
    details: Any | None = None


class ErrorResponse(BaseModel):
    """모든 오류가 동일하게 error 키를 사용하도록 감쌉니다."""

    # 실제 오류 내용은 중첩된 error 객체 아래에 둡니다.
    error: ErrorPayload


# 각 라우터가 OpenAPI에 같은 오류 구조를 표시하도록 공통 응답 설명을 제공합니다.
COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "요청한 리소스를 찾을 수 없음"},
    422: {"model": ErrorResponse, "description": "요청 입력 검증 실패"},
    500: {"model": ErrorResponse, "description": "예상하지 못한 서버 오류"},
    503: {"model": ErrorResponse, "description": "DB 또는 인증 설정을 사용할 수 없음"},
}


class HealthResponse(BaseModel):
    """서버 상태 응답입니다."""

    status: Literal["ok"]
    mode: str
    database: str | None = None


class WardrobeCreate(BaseModel):
    """옷장 등록 요청입니다."""

    # 앱 목록에 표시할 이름은 반드시 있어야 합니다.
    item_name: str = Field(min_length=1, max_length=120)
    # 나머지 값은 모르는 경우 null을 허용합니다.
    category: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    material: str | None = Field(default=None, max_length=120)
    product_reference: ProductReference | None = None
    image_reference: str | None = Field(default=None, max_length=500)
    care_wash_method: CareWashMethod | None = None
    care_gentle: bool | None = None
    care_temperature_celsius: int | None = Field(default=None, ge=0, le=100)
    care_wash_strength: WashStrength | None = None
    care_max_spin_rpm: int | None = Field(default=None, ge=0)
    care_spin_level: str | None = Field(default=None, max_length=40)
    care_dry_method: str | None = Field(default=None, max_length=80)
    color_family: ColorFamily | None = None
    color_bleed_risk: bool | None = None
    wash_separately: bool | None = None
    care_tumble_dry_allowed: bool | None = None
    care_tumble_dry_heat: str | None = Field(default=None, max_length=30)
    care_natural_dry: str | None = Field(default=None, max_length=50)
    care_dry_in_shade: bool | None = None
    weight_grams: int | None = Field(default=None, ge=0)
    care_notes: str | None = Field(default=None, max_length=500)
    source_type: SourceType = "user_input"
    verification_status: VerificationStatus = "unconfirmed"
    source_reference: str | None = Field(default=None, max_length=500)
    care_fields: list[CareFieldInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def prevent_duplicate_care_fields(self) -> "WardrobeCreate":
        """한 요청에 같은 필드를 두 번 보내는 모호함을 막습니다."""

        names = [field.field_name for field in self.care_fields]
        if len(names) != len(set(names)):
            raise ValueError("care_fields의 field_name은 중복될 수 없습니다.")
        return self


class WardrobeUpdate(BaseModel):
    """옷장 부분 수정 요청입니다."""

    # PATCH에서는 전달된 값만 바꾸기 위해 모든 필드를 선택적으로 둡니다.
    item_name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    material: str | None = Field(default=None, max_length=120)
    product_reference: ProductReference | None = None
    image_reference: str | None = Field(default=None, max_length=500)
    care_wash_method: CareWashMethod | None = None
    care_gentle: bool | None = None
    care_temperature_celsius: int | None = Field(default=None, ge=0, le=100)
    care_wash_strength: WashStrength | None = None
    care_max_spin_rpm: int | None = Field(default=None, ge=0)
    care_spin_level: str | None = Field(default=None, max_length=40)
    care_dry_method: str | None = Field(default=None, max_length=80)
    color_family: ColorFamily | None = None
    color_bleed_risk: bool | None = None
    wash_separately: bool | None = None
    care_tumble_dry_allowed: bool | None = None
    care_tumble_dry_heat: str | None = Field(default=None, max_length=30)
    care_natural_dry: str | None = Field(default=None, max_length=50)
    care_dry_in_shade: bool | None = None
    weight_grams: int | None = Field(default=None, ge=0)
    care_notes: str | None = Field(default=None, max_length=500)
    source_type: SourceType | None = None
    verification_status: VerificationStatus | None = None
    source_reference: str | None = Field(default=None, max_length=500)
    care_fields: list[CareFieldInput] | None = None

    @model_validator(mode="after")
    def prevent_duplicate_care_fields(self) -> "WardrobeUpdate":
        """수정 요청에서도 필드 이름을 한 번씩만 허용합니다."""

        if self.care_fields is None:
            return self
        names = [field.field_name for field in self.care_fields]
        if len(names) != len(set(names)):
            raise ValueError("care_fields의 field_name은 중복될 수 없습니다.")
        return self


class WardrobeRead(WardrobeCreate):
    """저장된 옷장 응답입니다."""

    # ORM 객체를 같은 이름의 응답으로 변환할 수 있게 합니다.
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    care_fields: list[CareFieldRead] = Field(default_factory=list)


class MachineModelSummary(BaseModel):
    """공용 기기 모델 목록의 요약 정보입니다."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    machine_key: str
    machine_type: str
    manufacturer: str
    model_name: str
    source_url: str | None
    verification_status: str
    verified_scope: str | None
    capacity_kg: float | None = None
    release_year: int | None = None
    capacity_source_url: str | None = None
    capacity_verification_status: str | None = None


class MachineCourseSettingRead(BaseModel):
    """실제로 확인된 코스 설정 조합입니다."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    setting_key: str
    temperature_celsius: int | None
    temperature_setting: str | None = None
    wash_strength: str | None = None
    spin_level: str | None
    spin_rpm: int | None = None
    water_level: str | None
    dry_level: str | None
    duration_minutes: int | None
    source_url: str | None
    verification_status: str
    is_default: bool = False
    manual_page: int | None = None
    evidence: str | None = None


class MachineCourseRead(BaseModel):
    """공용 기기 코스와 해당 설정 목록입니다."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    course_key: str
    name: str
    description: str | None
    settings: list[MachineCourseSettingRead]


class MachineCoursesResponse(BaseModel):
    """모델 하나의 코스 조회 응답입니다."""

    machine: MachineModelSummary
    courses: list[MachineCourseRead]


class UserMachineCreate(BaseModel):
    """사용자 기기 등록 요청입니다."""

    # washer·dryer 등 앱에서 구분할 기기 종류입니다.
    machine_type: str = Field(min_length=1, max_length=40)
    # 여러 기기를 등록했을 때 사용자가 구분할 이름입니다.
    display_name: str = Field(min_length=1, max_length=120)
    # 공용 모델을 선택하면 이 ID로 공식 코스 정보를 연결합니다.
    machine_model_id: str | None = None
    # 공용 모델이 없을 때 사용자가 직접 입력한 값입니다.
    manual_input: dict[str, Any] | None = None
    # 등록별 메모입니다.
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_model_or_manual(self) -> "UserMachineCreate":
        """공용 모델과 수동 입력 중 하나는 있어야 합니다."""

        # 두 입력이 모두 없으면 서버가 기기를 복원할 근거가 없으므로 요청을 거부합니다.
        if not self.machine_model_id and not self.manual_input:
            raise ValueError("machine_model_id 또는 manual_input 중 하나를 입력해 주세요.")
        return self


class UserMachineRead(BaseModel):
    """사용자 기기 재조회 응답입니다."""

    # ORM 객체에서 기본 필드를 읽기 위한 설정입니다.
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: str
    machine_type: str
    display_name: str
    machine_model_id: str | None
    manual_input: dict[str, Any] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # 공용 모델은 없을 수 있으므로 nullable로 둡니다.
    machine_model: MachineModelSummary | None = None


class DeleteResponse(BaseModel):
    """삭제 성공을 명확하게 알리는 응답입니다."""

    id: str
    deleted: Literal[True]
