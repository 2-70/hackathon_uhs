"""세탁 계획과 실제 설정 검증 API의 요청·응답 자료형입니다."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceEvidence(BaseModel):
    """판정에 사용한 필드 값과 출처입니다."""

    field_name: str
    value: Any | None = None
    knowledge_status: str
    source_type: str | None = None
    source_reference: str | None = None
    evidence: str | None = None


class DecisionReason(BaseModel):
    """모바일이 사용자에게 보여줄 구조화된 판정 이유입니다."""

    code: str
    message: str
    fields: list[str] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)


class ActualSetting(BaseModel):
    """실제 기기에서 함께 선택한 설정 조합입니다."""

    temperature_celsius: int | None = Field(default=None, ge=0, le=100)
    temperature_setting: str | None = Field(default=None, max_length=40)
    wash_strength: Literal["normal", "gentle", "very_gentle"] | None = None
    spin_rpm: int | None = Field(default=None, ge=0)
    spin_level: str | None = Field(default=None, max_length=40)
    water_level: str | None = Field(default=None, max_length=40)
    dry_level: str | None = Field(default=None, max_length=40)


class SettingSnapshot(ActualSetting):
    """계획에 선택된 DB 코스·설정 식별자까지 포함한 값입니다."""

    course_id: str
    course_key: str
    course_name: str
    setting_id: str
    setting_key: str
    is_default: bool
    verification_status: str
    source_url: str | None = None
    manual_page: int | None = None
    evidence: str | None = None


class PlanRequest(BaseModel):
    """최대 10벌의 최소 세탁 그룹 계산 요청입니다."""

    request_id: str = Field(min_length=1, max_length=120)
    input_version: int = Field(ge=0)
    wardrobe_item_ids: list[str] = Field(min_length=1, max_length=10)
    user_machine_id: str
    expected_item_versions: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_item_ids_and_versions(self) -> "PlanRequest":
        """중복 ID와 부분 버전 검사를 요청 단계에서 거부합니다."""

        if len(self.wardrobe_item_ids) != len(set(self.wardrobe_item_ids)):
            raise ValueError("wardrobe_item_ids에는 중복 ID를 넣을 수 없습니다.")
        if self.expected_item_versions is not None and set(
            self.expected_item_versions
        ) != set(self.wardrobe_item_ids):
            raise ValueError("expected_item_versions는 모든 의류 ID를 정확히 포함해야 합니다.")
        return self


class PlanItemResult(BaseModel):
    """기계세탁 그룹 밖으로 분류된 의류 한 건입니다."""

    wardrobe_item_id: str
    item_name: str
    reasons: list[DecisionReason]
    required_confirmation_fields: list[str] = Field(default_factory=list)


class DryingAdvice(BaseModel):
    """의류별 확인된 건조 조건과 추가 확인 항목입니다."""

    wardrobe_item_id: str
    tumble_dry_allowed: bool | None = None
    tumble_dry_heat: str | None = None
    natural_dry: str | None = None
    dry_in_shade: bool | None = None
    required_confirmation_fields: list[str] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)


class PlanGroup(BaseModel):
    """한 번에 함께 세탁할 의류와 실제 지원 설정입니다."""

    group_number: int
    wardrobe_item_ids: list[str]
    setting: SettingSnapshot
    capacity_status: Literal["verified", "not_verified", "exceeded"]
    total_weight_grams: int | None = None
    reasons: list[DecisionReason]


class AssignmentInvariant(BaseModel):
    """모든 입력 의류가 정확히 한 위치에 배정됐는지 보여줍니다."""

    valid: bool
    input_count: int
    assigned_count: int
    duplicate_item_ids: list[str] = Field(default_factory=list)
    missing_item_ids: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """계산 입력 스냅샷과 최소 세탁 계획 응답입니다."""

    request_id: str
    input_version: int
    input_fingerprint: str
    item_versions: dict[str, str]
    groups: list[PlanGroup]
    hand_wash_items: list[PlanItemResult]
    machine_wash_prohibited_items: list[PlanItemResult]
    pending_confirmation_items: list[PlanItemResult]
    unsupported_items: list[PlanItemResult]
    drying_advice: list[DryingAdvice]
    machine_wash_count: int
    capacity_status: Literal["verified", "not_verified", "exceeded"]
    assignment_invariant: AssignmentInvariant


class SettingsValidateRequest(BaseModel):
    """사용자가 실제 기기에 입력한 조합을 검증하는 요청입니다."""

    request_id: str = Field(min_length=1, max_length=120)
    input_version: int = Field(ge=0)
    wardrobe_item_ids: list[str] = Field(min_length=1, max_length=10)
    user_machine_id: str
    course_id: str | None = None
    setting_id: str | None = None
    actual_setting: ActualSetting | None = None
    expected_item_versions: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "SettingsValidateRequest":
        """검증 대상 설정과 의류 ID 구성을 확인합니다."""

        if len(self.wardrobe_item_ids) != len(set(self.wardrobe_item_ids)):
            raise ValueError("wardrobe_item_ids에는 중복 ID를 넣을 수 없습니다.")
        if self.setting_id is None and self.actual_setting is None:
            raise ValueError("setting_id 또는 actual_setting 중 하나가 필요합니다.")
        if self.expected_item_versions is not None and set(
            self.expected_item_versions
        ) != set(self.wardrobe_item_ids):
            raise ValueError("expected_item_versions는 모든 의류 ID를 정확히 포함해야 합니다.")
        return self


class ItemValidationResult(BaseModel):
    """한 의류에 대한 실제 설정 판정입니다."""

    wardrobe_item_id: str
    status: Literal["suitable", "needs_change", "unknown"]
    reasons: list[DecisionReason]


class SettingsValidateResponse(BaseModel):
    """실제 설정 판정과 가능한 대체 조합입니다."""

    request_id: str
    input_version: int
    input_fingerprint: str
    item_versions: dict[str, str]
    status: Literal["suitable", "needs_change", "unknown"]
    actual_setting: ActualSetting
    matched_setting_id: str | None = None
    violations: list[DecisionReason]
    unknown_fields: list[str]
    item_results: list[ItemValidationResult]
    alternatives: list[SettingSnapshot]
