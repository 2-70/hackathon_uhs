"""DB 데이터를 확인된 제약으로 바꾸고 계획·설정검증 응답을 구성합니다."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.errors import ApiError
from backend.app.db.models import MachineCourse, MachineModel, UserMachine, WardrobeItem
from backend.app.planning.engine import (
    ItemConstraint,
    MachineSettingValue,
    build_group_choices,
    check_item_setting,
    choose_group_setting,
    minimize_groups,
)
from backend.app.planning.schemas import (
    ActualSetting,
    AssignmentInvariant,
    DecisionReason,
    DryingAdvice,
    ItemValidationResult,
    PlanGroup,
    PlanItemResult,
    PlanRequest,
    PlanResponse,
    SettingSnapshot,
    SettingsValidateRequest,
    SettingsValidateResponse,
    SourceEvidence,
)


@dataclass(frozen=True)
class FieldFact:
    """의류 한 필드의 값과 확인 근거입니다."""

    field_name: str
    value: Any
    knowledge_status: str
    source_type: str | None
    source_reference: str | None
    evidence: str | None

    def source(self) -> SourceEvidence:
        """API 응답에 사용할 출처 구조로 변환합니다."""

        return SourceEvidence(
            field_name=self.field_name,
            value=self.value,
            knowledge_status=self.knowledge_status,
            source_type=self.source_type,
            source_reference=self.source_reference,
            evidence=self.evidence,
        )


@dataclass
class PlanningContext:
    """한 요청에서 실제로 읽은 의류·기기·설정 스냅샷입니다."""

    items: list[WardrobeItem]
    user_machine: UserMachine
    machine_model: MachineModel | None
    settings: list[MachineSettingValue]
    capacity_kg: float | None
    fingerprint: str
    item_versions: dict[str, str]


SCALAR_FIELDS = (
    "care_wash_method",
    "care_temperature_celsius",
    "care_wash_strength",
    "care_max_spin_rpm",
    "care_spin_level",
    "color_family",
    "color_bleed_risk",
    "wash_separately",
    "care_tumble_dry_allowed",
    "care_tumble_dry_heat",
    "care_natural_dry",
    "care_dry_in_shade",
    "weight_grams",
)


def _iso(value: datetime) -> str:
    """DB 시각을 예상 버전 비교에 사용할 ISO 문자열로 만듭니다."""

    return value.isoformat()


def _setting_snapshot(setting: MachineSettingValue) -> SettingSnapshot:
    """내부 설정 값을 API 응답 형태로 바꿉니다."""

    return SettingSnapshot(
        course_id=setting.course_id,
        course_key=setting.course_key,
        course_name=setting.course_name,
        setting_id=setting.setting_id,
        setting_key=setting.setting_key,
        temperature_celsius=setting.temperature_celsius,
        temperature_setting=setting.temperature_setting,
        wash_strength=setting.wash_strength,
        spin_rpm=setting.spin_rpm,
        spin_level=setting.spin_level,
        water_level=setting.water_level,
        dry_level=setting.dry_level,
        is_default=setting.is_default,
        verification_status=setting.verification_status,
        source_url=setting.source_url,
        manual_page=setting.manual_page,
        evidence=setting.evidence,
    )


def _db_settings(machine: MachineModel) -> list[MachineSettingValue]:
    """공용 모델의 확인된 실제 조합만 계산 입력으로 변환합니다."""

    result: list[MachineSettingValue] = []
    for course in machine.courses:
        for setting in course.settings:
            if setting.verification_status != "confirmed":
                continue
            result.append(
                MachineSettingValue(
                    course_id=course.id,
                    course_key=course.course_key,
                    course_name=course.name,
                    setting_id=setting.id,
                    setting_key=setting.setting_key,
                    temperature_celsius=setting.temperature_celsius,
                    temperature_setting=setting.temperature_setting,
                    wash_strength=setting.wash_strength,
                    spin_rpm=setting.spin_rpm,
                    spin_level=setting.spin_level,
                    water_level=setting.water_level,
                    dry_level=setting.dry_level,
                    is_default=setting.is_default,
                    verification_status=setting.verification_status,
                    source_url=setting.source_url,
                    manual_page=setting.manual_page,
                    evidence=setting.evidence,
                )
            )
    return result


def _manual_settings(machine: UserMachine) -> tuple[list[MachineSettingValue], float | None]:
    """사용자 수동 프로필의 확인된 조합을 공용 모델과 같은 형태로 읽습니다."""

    profile = machine.manual_input or {}
    if profile.get("verification_status") != "confirmed":
        raise ApiError(
            "MACHINE_PROFILE_INCOMPLETE",
            "수동 기기 프로필의 확인 상태가 confirmed여야 합니다.",
            422,
        )
    raw_settings = profile.get("settings")
    if not isinstance(raw_settings, list) or not raw_settings:
        raise ApiError(
            "MACHINE_SETTINGS_NOT_FOUND",
            "수동 기기에 확인된 설정 조합이 없습니다.",
            422,
        )
    settings: list[MachineSettingValue] = []
    for index, raw in enumerate(raw_settings):
        if not isinstance(raw, dict) or raw.get("verification_status") != "confirmed":
            continue
        settings.append(
            MachineSettingValue(
                course_id=str(raw.get("course_id") or f"manual-course-{index}"),
                course_key=str(raw.get("course_key") or f"manual-course-{index}"),
                course_name=str(raw.get("course_name") or "사용자 확인 코스"),
                setting_id=str(raw.get("setting_id") or f"manual-setting-{index}"),
                setting_key=str(raw.get("setting_key") or f"manual-setting-{index}"),
                temperature_celsius=raw.get("temperature_celsius"),
                temperature_setting=raw.get("temperature_setting"),
                wash_strength=raw.get("wash_strength"),
                spin_rpm=raw.get("spin_rpm"),
                spin_level=raw.get("spin_level"),
                water_level=raw.get("water_level"),
                dry_level=raw.get("dry_level"),
                is_default=bool(raw.get("is_default", False)),
                verification_status="confirmed",
                source_url=raw.get("source_url"),
                manual_page=raw.get("manual_page"),
                evidence=raw.get("evidence"),
            )
        )
    if not settings:
        raise ApiError(
            "MACHINE_SETTINGS_NOT_FOUND",
            "수동 기기에 confirmed 설정 조합이 없습니다.",
            422,
        )
    capacity = profile.get("capacity_kg")
    if profile.get("capacity_verification_status") != "confirmed":
        capacity = None
    return settings, float(capacity) if capacity is not None else None


def _fingerprint_payload(
    items: list[WardrobeItem],
    machine: UserMachine,
    model: MachineModel | None,
    settings: list[MachineSettingValue],
    capacity_kg: float | None,
) -> dict[str, Any]:
    """비밀정보 없이 실제 계산값 전체를 정렬 가능한 사전으로 만듭니다."""

    item_values = []
    for item in sorted(items, key=lambda value: value.id):
        item_values.append(
            {
                "id": item.id,
                "updated_at": _iso(item.updated_at),
                "values": {name: getattr(item, name) for name in SCALAR_FIELDS},
                "care_fields": [
                    {
                        "field_name": field.field_name,
                        "value": field.value_json,
                        "knowledge_status": field.knowledge_status,
                        "source_type": field.source_type,
                        "source_reference": field.source_reference,
                        "evidence": field.evidence,
                        "conflicting_values": field.conflicting_values,
                        "updated_at": _iso(field.updated_at),
                    }
                    for field in sorted(item.care_fields, key=lambda value: value.field_name)
                ],
            }
        )
    setting_values = [setting.__dict__ for setting in sorted(settings, key=lambda value: value.setting_id)]
    return {
        "items": item_values,
        "user_machine": {
            "id": machine.id,
            "updated_at": _iso(machine.updated_at),
            "machine_model_id": machine.machine_model_id,
            "manual_input": machine.manual_input,
        },
        "machine_model": None
        if model is None
        else {
            "id": model.id,
            "updated_at": _iso(model.updated_at),
            "capacity_kg": model.capacity_kg,
            "capacity_verification_status": model.capacity_verification_status,
        },
        "capacity_kg": capacity_kg,
        "settings": setting_values,
    }


def _load_context(
    db: Session,
    owner_id: str,
    item_ids: list[str],
    user_machine_id: str,
    expected_versions: dict[str, str] | None,
) -> PlanningContext:
    """소유권·버전을 검증하고 한 요청의 일관된 계산 스냅샷을 만듭니다."""

    item_statement = (
        select(WardrobeItem)
        .options(selectinload(WardrobeItem.care_fields))
        .where(WardrobeItem.id.in_(item_ids))
    )
    found_items = list(db.scalars(item_statement).unique().all())
    found_by_id = {item.id: item for item in found_items}
    missing = sorted(set(item_ids) - set(found_by_id))
    if missing:
        raise ApiError(
            "WARDROBE_NOT_FOUND",
            "요청한 옷장 항목 일부를 찾을 수 없습니다.",
            404,
            {"item_ids": missing},
        )
    foreign = sorted(item.id for item in found_items if item.owner_id != owner_id)
    if foreign:
        raise ApiError(
            "WARDROBE_NOT_OWNED",
            "현재 사용자의 옷장 항목만 사용할 수 있습니다.",
            404,
            {"item_ids": foreign},
        )
    # 요청 순서와 무관한 계산을 위해 ID 순서로 정렬합니다.
    items = [found_by_id[item_id] for item_id in sorted(item_ids)]
    item_versions = {item.id: _iso(item.updated_at) for item in items}
    if expected_versions is not None:
        stale = sorted(
            item_id
            for item_id, expected in expected_versions.items()
            if item_versions[item_id] != expected
        )
        if stale:
            raise ApiError(
                "STALE_INPUT",
                "옷 정보가 요청 준비 이후 변경되었습니다. 최신 값으로 다시 계산해 주세요.",
                409,
                {"item_ids": stale, "current_versions": item_versions},
            )

    machine_statement = (
        select(UserMachine)
        .options(
            selectinload(UserMachine.machine_model)
            .selectinload(MachineModel.courses)
            .selectinload(MachineCourse.settings)
        )
        .where(UserMachine.id == user_machine_id)
    )
    user_machine = db.scalar(machine_statement)
    if user_machine is None:
        raise ApiError("USER_MACHINE_NOT_FOUND", "등록한 기기를 찾을 수 없습니다.", 404)
    if user_machine.owner_id != owner_id:
        raise ApiError(
            "USER_MACHINE_NOT_OWNED", "현재 사용자의 기기만 사용할 수 있습니다.", 404
        )

    model = user_machine.machine_model
    if model is not None:
        settings = _db_settings(model)
        capacity = (
            model.capacity_kg
            if model.capacity_verification_status == "confirmed"
            else None
        )
    else:
        settings, capacity = _manual_settings(user_machine)
    if not settings:
        raise ApiError(
            "MACHINE_SETTINGS_NOT_FOUND",
            "선택한 기기에 confirmed 설정 조합이 없습니다.",
            422,
        )

    payload = _fingerprint_payload(items, user_machine, model, settings, capacity)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return PlanningContext(
        items=items,
        user_machine=user_machine,
        machine_model=model,
        settings=settings,
        capacity_kg=capacity,
        fingerprint=sha256(encoded).hexdigest(),
        item_versions=item_versions,
    )


def _facts(item: WardrobeItem) -> dict[str, FieldFact]:
    """필드별 행을 우선하고 기존 scalar는 item 확인 상태로 fallback합니다."""

    result: dict[str, FieldFact] = {}
    rows = {row.field_name: row for row in item.care_fields}
    for field_name in SCALAR_FIELDS:
        row = rows.get(field_name)
        if row is not None:
            result[field_name] = FieldFact(
                field_name=field_name,
                value=row.value_json,
                knowledge_status=row.knowledge_status,
                source_type=row.source_type,
                source_reference=row.source_reference,
                evidence=row.evidence,
            )
            continue
        value = getattr(item, field_name)
        status = item.verification_status if value is not None else "needs_confirmation"
        result[field_name] = FieldFact(
            field_name=field_name,
            value=value,
            knowledge_status=status,
            source_type=item.source_type if value is not None else None,
            source_reference=item.source_reference if value is not None else None,
            evidence=None,
        )
    return result


def _is_confirmed(fact: FieldFact) -> bool:
    """값이 있고 confirmed인 경우만 계산 가능한 사실로 봅니다."""

    return fact.knowledge_status == "confirmed" and fact.value is not None


def _missing_core_fields(facts: dict[str, FieldFact]) -> list[str]:
    """기계세탁 가능성을 판단하는 데 필요한 핵심 필드를 찾습니다."""

    required = (
        "care_wash_method",
        "care_temperature_celsius",
        "care_wash_strength",
        "color_family",
        "color_bleed_risk",
        "wash_separately",
    )
    missing = [name for name in required if not _is_confirmed(facts[name])]
    if _is_confirmed(facts["color_family"]) and facts["color_family"].value == "unknown":
        missing.append("color_family")

    rpm = facts["care_max_spin_rpm"]
    level = facts["care_spin_level"]
    spin_is_known = _is_confirmed(rpm) or _is_confirmed(level)
    spin_not_applicable = (
        rpm.knowledge_status == "not_applicable" or level.knowledge_status == "not_applicable"
    )
    if not spin_is_known and not spin_not_applicable:
        missing.append("spin_limit")
    return sorted(set(missing))


def _constraint(item: WardrobeItem, facts: dict[str, FieldFact]) -> ItemConstraint:
    """핵심 필드가 모두 확인된 의류를 순수 계산 자료형으로 변환합니다."""

    return ItemConstraint(
        item_id=item.id,
        item_name=item.item_name,
        max_temperature_celsius=int(facts["care_temperature_celsius"].value),
        max_wash_strength=str(facts["care_wash_strength"].value),
        max_spin_rpm=(
            int(facts["care_max_spin_rpm"].value)
            if _is_confirmed(facts["care_max_spin_rpm"])
            else None
        ),
        spin_level=(
            str(facts["care_spin_level"].value)
            if _is_confirmed(facts["care_spin_level"])
            else None
        ),
        spin_not_applicable=(
            facts["care_max_spin_rpm"].knowledge_status == "not_applicable"
            or facts["care_spin_level"].knowledge_status == "not_applicable"
        ),
        color_family=str(facts["color_family"].value),
        color_bleed_risk=bool(facts["color_bleed_risk"].value),
        wash_separately=bool(facts["wash_separately"].value),
        weight_grams=(
            int(facts["weight_grams"].value)
            if _is_confirmed(facts["weight_grams"])
            else None
        ),
    )


def _reason(
    code: str,
    message: str,
    field_names: list[str],
    facts: dict[str, FieldFact],
) -> DecisionReason:
    """이유와 해당 필드 출처를 한 객체로 묶습니다."""

    return DecisionReason(
        code=code,
        message=message,
        fields=field_names,
        sources=[facts[name].source() for name in field_names if name in facts],
    )


def _outside_result(
    item: WardrobeItem,
    reason: DecisionReason,
    required: list[str] | None = None,
) -> PlanItemResult:
    """그룹 밖 분류의 반복 응답 구조를 만듭니다."""

    return PlanItemResult(
        wardrobe_item_id=item.id,
        item_name=item.item_name,
        reasons=[reason],
        required_confirmation_fields=required or [],
    )


def _drying_advice(item: WardrobeItem, facts: dict[str, FieldFact]) -> DryingAdvice:
    """확인된 건조 값만 노출하고 나머지는 확인 필요로 표시합니다."""

    names = (
        "care_tumble_dry_allowed",
        "care_tumble_dry_heat",
        "care_natural_dry",
        "care_dry_in_shade",
    )
    missing = [
        name
        for name in names
        if facts[name].knowledge_status not in {"confirmed", "not_applicable"}
    ]
    return DryingAdvice(
        wardrobe_item_id=item.id,
        tumble_dry_allowed=(
            bool(facts["care_tumble_dry_allowed"].value)
            if _is_confirmed(facts["care_tumble_dry_allowed"])
            else None
        ),
        tumble_dry_heat=(
            str(facts["care_tumble_dry_heat"].value)
            if _is_confirmed(facts["care_tumble_dry_heat"])
            else None
        ),
        natural_dry=(
            str(facts["care_natural_dry"].value)
            if _is_confirmed(facts["care_natural_dry"])
            else None
        ),
        dry_in_shade=(
            bool(facts["care_dry_in_shade"].value)
            if _is_confirmed(facts["care_dry_in_shade"])
            else None
        ),
        required_confirmation_fields=missing,
        sources=[facts[name].source() for name in names],
    )


def create_plan(db: Session, owner_id: str, request: PlanRequest) -> PlanResponse:
    """분류 우선순위와 부분집합 DP를 적용해 최소 세탁 계획을 만듭니다."""

    context = _load_context(
        db,
        owner_id,
        request.wardrobe_item_ids,
        request.user_machine_id,
        request.expected_item_versions,
    )
    hand_wash: list[PlanItemResult] = []
    prohibited: list[PlanItemResult] = []
    pending: list[PlanItemResult] = []
    unsupported: list[PlanItemResult] = []
    eligible: list[ItemConstraint] = []
    facts_by_id: dict[str, dict[str, FieldFact]] = {}

    for item in context.items:
        facts = _facts(item)
        facts_by_id[item.id] = facts
        wash_method = facts["care_wash_method"]
        # 확인된 금지와 손세탁을 정보 부족보다 먼저 분류합니다.
        if _is_confirmed(wash_method) and wash_method.value == "do_not_wash":
            prohibited.append(
                _outside_result(
                    item,
                    _reason(
                        "MACHINE_WASH_PROHIBITED",
                        "확인된 관리 정보가 물세탁 또는 기계세탁을 금지합니다.",
                        ["care_wash_method"],
                        facts,
                    ),
                )
            )
            continue
        if _is_confirmed(wash_method) and wash_method.value == "hand_wash":
            hand_wash.append(
                _outside_result(
                    item,
                    _reason(
                        "HAND_WASH_ONLY",
                        "확인된 관리 정보가 손세탁 전용입니다.",
                        ["care_wash_method"],
                        facts,
                    ),
                )
            )
            continue

        missing = _missing_core_fields(facts)
        if missing:
            pending.append(
                _outside_result(
                    item,
                    _reason(
                        "CARE_INFORMATION_INCOMPLETE",
                        "안전한 기계세탁 판단에 필요한 정보가 부족하거나 충돌합니다.",
                        [name for name in missing if name in facts],
                        facts,
                    ),
                    missing,
                )
            )
            continue

        constraint = _constraint(item, facts)
        setting, capacity_status, _, comparison_fields = choose_group_setting(
            [constraint], context.settings, context.capacity_kg
        )
        if setting is not None:
            eligible.append(constraint)
        elif comparison_fields and any(
            name in {"temperature_celsius", "wash_strength", "spin_rpm", "spin_level", "spin_level_order"}
            for name in comparison_fields
        ):
            pending.append(
                _outside_result(
                    item,
                    _reason(
                        "MACHINE_SETTING_NOT_COMPARABLE",
                        "기기의 설정 근거가 부족해 의류 제한과 비교할 수 없습니다.",
                        [],
                        facts,
                    ),
                    comparison_fields,
                )
            )
        else:
            fields = ["weight_grams"] if capacity_status == "exceeded" else []
            unsupported.append(
                _outside_result(
                    item,
                    _reason(
                        "NO_SUPPORTED_SETTING",
                        "확인된 의류 조건을 만족하는 실제 기기 설정 조합이 없습니다.",
                        fields,
                        facts,
                    ),
                )
            )

    choices = build_group_choices(eligible, context.settings, context.capacity_kg)
    try:
        selected_groups = minimize_groups(eligible, choices)
    except ValueError as exc:
        # 단일 의류 가능성을 먼저 확인했으므로 이 경우는 엔진 invariant 위반입니다.
        raise ApiError("PLAN_INVARIANT_FAILED", str(exc), 500) from exc

    groups = []
    for index, choice in enumerate(selected_groups, start=1):
        reason_sources = []
        for item_id in choice.item_ids:
            reason_sources.extend(
                facts_by_id[item_id][name].source()
                for name in ("care_temperature_celsius", "care_wash_strength")
            )
        groups.append(
            PlanGroup(
                group_number=index,
                wardrobe_item_ids=list(choice.item_ids),
                setting=_setting_snapshot(choice.setting),
                capacity_status=choice.capacity_status,
                total_weight_grams=choice.total_weight_grams,
                reasons=[
                    DecisionReason(
                        code="COMMON_SUPPORTED_SETTING",
                        message="모든 의류 제한을 만족하는 실제 지원 설정 조합입니다.",
                        fields=["care_temperature_celsius", "care_wash_strength"],
                        sources=reason_sources,
                    )
                ],
            )
        )

    assigned_ids = [item_id for group in groups for item_id in group.wardrobe_item_ids]
    assigned_ids += [
        item.wardrobe_item_id
        for collection in (hand_wash, prohibited, pending, unsupported)
        for item in collection
    ]
    counts = Counter(assigned_ids)
    duplicates = sorted(item_id for item_id, count in counts.items() if count > 1)
    missing_ids = sorted(set(request.wardrobe_item_ids) - set(assigned_ids))
    invariant = AssignmentInvariant(
        valid=not duplicates and not missing_ids and len(assigned_ids) == len(request.wardrobe_item_ids),
        input_count=len(request.wardrobe_item_ids),
        assigned_count=len(assigned_ids),
        duplicate_item_ids=duplicates,
        missing_item_ids=missing_ids,
    )
    if not invariant.valid:
        raise ApiError("PLAN_INVARIANT_FAILED", "계획 배정 invariant를 만족하지 못했습니다.", 500)

    capacity_status = "verified"
    statuses = [group.capacity_status for group in groups]
    if "exceeded" in statuses:
        capacity_status = "exceeded"
    elif not statuses or "not_verified" in statuses:
        capacity_status = "not_verified"
    return PlanResponse(
        request_id=request.request_id,
        input_version=request.input_version,
        input_fingerprint=context.fingerprint,
        item_versions=context.item_versions,
        groups=groups,
        hand_wash_items=hand_wash,
        machine_wash_prohibited_items=prohibited,
        pending_confirmation_items=pending,
        unsupported_items=unsupported,
        drying_advice=[_drying_advice(item, facts_by_id[item.id]) for item in context.items],
        machine_wash_count=len(groups),
        capacity_status=capacity_status,
        assignment_invariant=invariant,
    )


def _actual_from_setting(setting: MachineSettingValue) -> ActualSetting:
    """저장된 설정 조합에서 실제 입력값 부분만 추립니다."""

    return ActualSetting(
        temperature_celsius=setting.temperature_celsius,
        temperature_setting=setting.temperature_setting,
        wash_strength=setting.wash_strength,
        spin_rpm=setting.spin_rpm,
        spin_level=setting.spin_level,
        water_level=setting.water_level,
        dry_level=setting.dry_level,
    )


def _matches_actual(actual: ActualSetting, setting: MachineSettingValue) -> bool:
    """사용자가 보낸 값이 저장된 실제 조합과 모두 일치하는지 확인합니다."""

    for name, value in actual.model_dump(exclude_none=True).items():
        if getattr(setting, name) != value:
            return False
    return True


def _actual_is_complete(actual: ActualSetting) -> bool:
    """미지원 판정을 내릴 만큼 핵심 설정이 입력됐는지 확인합니다."""

    has_temperature = actual.temperature_celsius is not None or actual.temperature_setting is not None
    has_spin = actual.spin_rpm is not None or actual.spin_level is not None
    return has_temperature and actual.wash_strength is not None and has_spin


def validate_settings(
    db: Session,
    owner_id: str,
    request: SettingsValidateRequest,
) -> SettingsValidateResponse:
    """추천값이 아니라 사용자의 실제 입력 조합 자체를 독립 검증합니다."""

    context = _load_context(
        db,
        owner_id,
        request.wardrobe_item_ids,
        request.user_machine_id,
        request.expected_item_versions,
    )
    options = [
        setting
        for setting in context.settings
        if request.course_id is None or setting.course_id == request.course_id
    ]
    selected = next(
        (setting for setting in options if setting.setting_id == request.setting_id), None
    )
    if request.setting_id is not None and selected is None:
        raise ApiError(
            "SETTING_NOT_SUPPORTED",
            "선택한 설정은 현재 사용자 기기의 지원 조합이 아닙니다.",
            422,
        )
    if selected is not None:
        if request.actual_setting is not None and not _matches_actual(request.actual_setting, selected):
            raise ApiError(
                "CONFLICTING_INPUT",
                "setting_id의 저장값과 actual_setting이 다릅니다.",
                422,
            )
        actual = _actual_from_setting(selected)
        matched = selected
        support_unknown = False
    else:
        # 스키마 validator가 둘 중 하나를 보장하므로 여기서는 actual_setting이 존재합니다.
        actual = request.actual_setting or ActualSetting()
        matching = [setting for setting in options if _matches_actual(actual, setting)]
        complete = _actual_is_complete(actual)
        matched = matching[0] if complete and matching else None
        support_unknown = not complete

    violations: list[DecisionReason] = []
    unknown_fields: set[str] = set()
    item_results: list[ItemValidationResult] = []
    constraints: list[ItemConstraint] = []

    if matched is None and not support_unknown:
        violations.append(
            DecisionReason(
                code="SETTING_NOT_SUPPORTED",
                message="입력한 값의 조합은 현재 기기의 confirmed 지원 조합에 없습니다.",
                fields=[],
            )
        )
    elif support_unknown:
        unknown_fields.add("actual_setting")

    # 지원 조합과 정확히 일치하지 않아도 확인된 값 위반은 우선 판정합니다.
    comparison_setting = MachineSettingValue(
        course_id=matched.course_id if matched else request.course_id or "actual",
        course_key=matched.course_key if matched else "actual",
        course_name=matched.course_name if matched else "실제 입력",
        setting_id=matched.setting_id if matched else "actual",
        setting_key=matched.setting_key if matched else "actual",
        temperature_celsius=actual.temperature_celsius,
        temperature_setting=actual.temperature_setting,
        wash_strength=actual.wash_strength,
        spin_rpm=actual.spin_rpm,
        spin_level=actual.spin_level,
        water_level=actual.water_level,
        dry_level=actual.dry_level,
        is_default=False,
        verification_status="confirmed" if matched else "unconfirmed",
    )

    for item in context.items:
        facts = _facts(item)
        wash = facts["care_wash_method"]
        item_reasons: list[DecisionReason] = []
        if _is_confirmed(wash) and wash.value in {"do_not_wash", "hand_wash"}:
            item_reasons.append(
                _reason(
                    "MACHINE_WASH_NOT_ALLOWED",
                    "이 의류는 확인된 관리 방법상 기계세탁할 수 없습니다.",
                    ["care_wash_method"],
                    facts,
                )
            )
            violations.extend(item_reasons)
            item_results.append(
                ItemValidationResult(
                    wardrobe_item_id=item.id, status="needs_change", reasons=item_reasons
                )
            )
            continue
        missing = _missing_core_fields(facts)
        if missing:
            unknown_fields.update(missing)
            reason = _reason(
                "CARE_INFORMATION_INCOMPLETE",
                "의류 조건이 부족하거나 충돌해 일부 비교를 완료할 수 없습니다.",
                [name for name in missing if name in facts],
                facts,
            )
            item_results.append(
                ItemValidationResult(
                    wardrobe_item_id=item.id, status="unknown", reasons=[reason]
                )
            )
            continue
        constraint = _constraint(item, facts)
        constraints.append(constraint)
        check = check_item_setting(constraint, comparison_setting)
        if check.violations:
            reason = _reason(
                "CARE_LIMIT_VIOLATION",
                "실제 설정이 확인된 의류 제한을 위반합니다.",
                [
                    {
                        "temperature_celsius": "care_temperature_celsius",
                        "wash_strength": "care_wash_strength",
                        "spin_rpm": "care_max_spin_rpm",
                    }.get(name, name)
                    for name in check.violations
                ],
                facts,
            )
            violations.append(reason)
            item_results.append(
                ItemValidationResult(
                    wardrobe_item_id=item.id, status="needs_change", reasons=[reason]
                )
            )
        elif check.unknown_fields:
            unknown_fields.update(check.unknown_fields)
            reason = _reason(
                "SETTING_COMPARISON_UNKNOWN",
                "입력값 또는 비교 근거가 부족해 일부 조건을 판단할 수 없습니다.",
                [],
                facts,
            )
            item_results.append(
                ItemValidationResult(
                    wardrobe_item_id=item.id, status="unknown", reasons=[reason]
                )
            )
        else:
            item_results.append(
                ItemValidationResult(
                    wardrobe_item_id=item.id,
                    status="suitable",
                    reasons=[
                        _reason(
                            "CARE_LIMITS_SATISFIED",
                            "실제 설정이 확인된 의류 제한을 모두 만족합니다.",
                            ["care_temperature_celsius", "care_wash_strength"],
                            facts,
                        )
                    ],
                )
            )

    # 확인된 위반이 하나라도 있으면 unknown보다 needs_change가 우선합니다.
    if violations:
        status = "needs_change"
    elif unknown_fields:
        status = "unknown"
    else:
        status = "suitable"

    alternatives: list[SettingSnapshot] = []
    if len(constraints) == len(context.items):
        for option in context.settings:
            chosen, _, _, _ = choose_group_setting(
                constraints, [option], context.capacity_kg
            )
            if chosen is not None:
                alternatives.append(_setting_snapshot(chosen))
    alternatives.sort(key=lambda value: (not value.is_default, value.course_key, value.setting_key))
    return SettingsValidateResponse(
        request_id=request.request_id,
        input_version=request.input_version,
        input_fingerprint=context.fingerprint,
        item_versions=context.item_versions,
        status=status,
        actual_setting=actual,
        matched_setting_id=matched.setting_id if matched else None,
        violations=violations,
        unknown_fields=sorted(unknown_fields),
        item_results=item_results,
        alternatives=alternatives,
    )
