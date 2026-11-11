"""DB나 HTTP에 의존하지 않는 세탁 조건 비교와 부분집합 DP입니다."""

from dataclasses import dataclass, field
from itertools import combinations


@dataclass(frozen=True)
class MachineSettingValue:
    """실제 기기에서 함께 선택 가능한 설정 조합 한 건입니다."""

    course_id: str
    course_key: str
    course_name: str
    setting_id: str
    setting_key: str
    temperature_celsius: int | None
    temperature_setting: str | None
    wash_strength: str | None
    spin_rpm: int | None
    spin_level: str | None
    water_level: str | None
    dry_level: str | None
    is_default: bool
    verification_status: str
    source_url: str | None = None
    manual_page: int | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class ItemConstraint:
    """계획 계산에 필요한 의류의 확인된 제한값입니다."""

    item_id: str
    item_name: str
    max_temperature_celsius: int
    max_wash_strength: str
    max_spin_rpm: int | None
    spin_level: str | None
    spin_not_applicable: bool
    color_family: str
    color_bleed_risk: bool
    wash_separately: bool
    weight_grams: int | None


@dataclass
class CompatibilityResult:
    """설정 비교 결과의 확인된 위반과 판단 불가 항목입니다."""

    compatible: bool
    violations: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GroupChoice:
    """DP가 선택할 수 있는 의류 부분집합과 대표 설정입니다."""

    mask: int
    item_ids: tuple[str, ...]
    setting: MachineSettingValue
    capacity_status: str
    total_weight_grams: int | None


# 숫자가 클수록 더 강한 세탁이라는 명시적인 도메인 순서입니다.
WASH_STRENGTH_RANK = {"very_gentle": 0, "gentle": 1, "normal": 2}


def check_item_setting(
    item: ItemConstraint,
    setting: MachineSettingValue,
) -> CompatibilityResult:
    """의류 한 벌과 실제 지원 설정의 온도·강도·탈수를 비교합니다."""

    violations: list[str] = []
    unknown_fields: list[str] = []

    # 숫자 최대 온도와 비교하려면 기기에도 근거 있는 섭씨 값이 필요합니다.
    if setting.temperature_celsius is None:
        unknown_fields.append("temperature_celsius")
    elif setting.temperature_celsius > item.max_temperature_celsius:
        violations.append("temperature_celsius")

    # 세탁 강도는 도메인에서 정의한 3단계 안에서만 순서를 비교합니다.
    if setting.wash_strength not in WASH_STRENGTH_RANK:
        unknown_fields.append("wash_strength")
    elif WASH_STRENGTH_RANK[setting.wash_strength] > WASH_STRENGTH_RANK[item.max_wash_strength]:
        violations.append("wash_strength")

    # RPM 제한은 양쪽 모두 숫자일 때만 비교합니다.
    if item.max_spin_rpm is not None:
        if setting.spin_rpm is None:
            unknown_fields.append("spin_rpm")
        elif setting.spin_rpm > item.max_spin_rpm:
            violations.append("spin_rpm")
    # 단계명은 모델별 순서 근거가 없으므로 같은 이름만 안전하게 확인합니다.
    elif item.spin_level is not None:
        if setting.spin_level is None:
            unknown_fields.append("spin_level")
        elif setting.spin_level != item.spin_level:
            unknown_fields.append("spin_level_order")
    elif not item.spin_not_applicable:
        unknown_fields.append("spin_limit")

    return CompatibilityResult(
        compatible=not violations and not unknown_fields,
        violations=violations,
        unknown_fields=unknown_fields,
    )


def _separation_violations(items: list[ItemConstraint]) -> list[str]:
    """단독세탁과 밝은색·어두운색 혼합 규칙을 확인합니다."""

    violations: list[str] = []
    if len(items) > 1 and any(item.wash_separately for item in items):
        violations.append("wash_separately")

    # 명시적으로 확인된 light와 dark는 안전을 위해 같은 그룹에 섞지 않습니다.
    color_families = {item.color_family for item in items}
    if "light" in color_families and "dark" in color_families:
        violations.append("color_family")
    return violations


def choose_group_setting(
    items: list[ItemConstraint],
    settings: list[MachineSettingValue],
    capacity_kg: float | None,
) -> tuple[MachineSettingValue | None, str, int | None, list[str]]:
    """부분집합에 공통으로 맞는 실제 설정을 안정적으로 하나 선택합니다."""

    separation_violations = _separation_violations(items)
    if separation_violations:
        return None, "not_verified", None, separation_violations

    # 모든 옷 무게와 기기 용량을 알 때만 합계를 제한으로 사용합니다.
    all_weights_known = all(item.weight_grams is not None for item in items)
    total_weight = sum(item.weight_grams or 0 for item in items) if all_weights_known else None
    capacity_status = "not_verified"
    if capacity_kg is not None and total_weight is not None:
        capacity_status = "verified"
        if total_weight > round(capacity_kg * 1000):
            return None, "exceeded", total_weight, ["capacity"]

    compatible_settings = []
    unknown_fields: set[str] = set()
    for setting in settings:
        checks = [check_item_setting(item, setting) for item in items]
        if all(check.compatible for check in checks):
            compatible_settings.append(setting)
        for check in checks:
            unknown_fields.update(check.unknown_fields)

    if not compatible_settings:
        return None, capacity_status, total_weight, sorted(unknown_fields)

    # 확인된 기본 조합을 먼저, 이후 코스·설정 키 순서로 결정해 결과를 재현 가능하게 합니다.
    selected = min(
        compatible_settings,
        key=lambda value: (
            not value.is_default,
            value.course_key,
            value.setting_key,
            value.setting_id,
        ),
    )
    return selected, capacity_status, total_weight, []


def build_group_choices(
    items: list[ItemConstraint],
    settings: list[MachineSettingValue],
    capacity_kg: float | None,
) -> list[GroupChoice]:
    """모든 비어 있지 않은 부분집합 중 실제로 세탁 가능한 후보만 만듭니다."""

    choices: list[GroupChoice] = []
    item_count = len(items)
    for size in range(1, item_count + 1):
        for indexes in combinations(range(item_count), size):
            subset = [items[index] for index in indexes]
            setting, capacity_status, total_weight, _ = choose_group_setting(
                subset, settings, capacity_kg
            )
            if setting is None:
                continue
            mask = sum(1 << index for index in indexes)
            choices.append(
                GroupChoice(
                    mask=mask,
                    item_ids=tuple(sorted(item.item_id for item in subset)),
                    setting=setting,
                    capacity_status=capacity_status,
                    total_weight_grams=total_weight,
                )
            )
    return choices


def _partition_signature(groups: tuple[GroupChoice, ...]) -> tuple:
    """그룹 수가 같은 계획을 입력 순서와 무관한 안정적인 키로 바꿉니다."""

    return tuple(
        sorted(
            (
                group.item_ids,
                group.setting.course_key,
                group.setting.setting_key,
                group.setting.setting_id,
            )
            for group in groups
        )
    )


def minimize_groups(items: list[ItemConstraint], choices: list[GroupChoice]) -> list[GroupChoice]:
    """부분집합 DP로 모든 의류를 덮는 최소 그룹 계획을 계산합니다."""

    if not items:
        return []
    full_mask = (1 << len(items)) - 1
    choices_by_first: dict[int, list[GroupChoice]] = {}
    for choice in choices:
        first_index = (choice.mask & -choice.mask).bit_length() - 1
        choices_by_first.setdefault(first_index, []).append(choice)

    # dp[mask]는 mask에 포함된 옷을 덮는 현재 최선의 그룹 튜플입니다.
    dp: dict[int, tuple[GroupChoice, ...]] = {0: ()}
    for mask in range(full_mask + 1):
        current = dp.get(mask)
        if current is None or mask == full_mask:
            continue
        remaining = full_mask ^ mask
        first_unassigned = (remaining & -remaining).bit_length() - 1
        for choice in choices_by_first.get(first_unassigned, []):
            if choice.mask & mask:
                continue
            next_mask = mask | choice.mask
            candidate = current + (choice,)
            previous = dp.get(next_mask)
            if previous is None or (
                len(candidate), _partition_signature(candidate)
            ) < (len(previous), _partition_signature(previous)):
                dp[next_mask] = candidate

    result = dp.get(full_mask)
    if result is None:
        raise ValueError("모든 기계세탁 후보를 배정할 수 있는 분할이 없습니다.")
    return sorted(result, key=lambda group: (group.item_ids, group.setting.setting_key))
