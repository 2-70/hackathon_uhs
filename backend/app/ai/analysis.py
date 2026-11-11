import re
from decimal import Decimal
from typing import Literal
from unicodedata import normalize

from .schemas import (
    AnalysisResponse,
    AnalyzedField,
    GarmentReadings,
    LabelReadings,
    PhotoIssue,
    PhotoReadings,
    PhotoRequest,
    RequestedPhotoType,
)

WASH_GUIDANCE = {
    "machine_wash": "세탁기로 세탁할 수 있어요.",
    "hand_wash": "손세탁하세요.",
    "do_not_wash": "물세탁을 피하세요.",
}
WASH_CYCLE_GUIDANCE = {
    "normal": "일반 세탁 강도를 사용할 수 있어요.",
    "gentle": "약하게 세탁하세요.",
    "very_gentle": "아주 약하게 세탁하세요.",
}
DRYER_GUIDANCE = {
    "no_heat": "건조기는 열 없이 사용하세요.",
    "low": "건조기는 저온으로 사용하세요.",
    "normal": "건조기는 일반 온도로 사용할 수 있어요.",
}
NATURAL_DRY_GUIDANCE = {
    "line_dry": "옷을 걸어서 말리세요.",
    "drip_line_dry": "물이 떨어지는 상태로 걸어서 말리세요.",
    "flat_dry": "옷을 평평하게 펴서 말리세요.",
    "drip_flat_dry": "물이 떨어지는 상태로 평평하게 펴서 말리세요.",
}
SORTING_GUIDANCE = {
    "similar_colors": "물세탁이 가능한 옷이라면 비슷한 색끼리 모아 세탁하세요.",
    "separate_dark_colors": "물세탁이 가능한 옷이라면 밝은 옷과 분리해 세탁하세요.",
}


def new_label_photo_request() -> PhotoRequest:
    return PhotoRequest(
        image_type="care_label",
        instructions=(
            "옷을 뒤집어 안쪽 옆 솔기나 목 뒤의 세탁 라벨을 찾아 주세요. "
            "물통 모양의 세탁 기호와 네모 모양의 건조 기호, 기호 안의 숫자가 보이도록 라벨을 펼쳐 가까이 찍어 주세요."
        ),
    )


def request_label_photo(care: LabelReadings, issue: PhotoIssue | None = None) -> PhotoRequest | None:
    missing_washing = care.wash_method is None or (
        care.wash_method.value != "do_not_wash" and care.max_wash_temperature_c is None
    )
    missing_drying = care.natural_dry is None and (
        care.tumble_dry_allowed is None or (care.tumble_dry_allowed.value and care.tumble_dry_heat is None)
    )
    if not (missing_washing or missing_drying):
        return None
    if issue == "wrong_label":
        return new_label_photo_request()

    washing_symbols = "물통 모양의 세탁 기호와 안에 적힌 숫자"
    drying_symbols = "네모 모양의 건조 기호와 점 또는 X 표시"
    if missing_washing and missing_drying:
        symbols = f"{washing_symbols}, {drying_symbols}"
    elif missing_washing:
        symbols = washing_symbols
    else:
        symbols = drying_symbols

    if issue == "missing_information":
        instructions = f"같은 옷의 다른 안쪽 라벨이나 태그 뒷면에 {symbols} 부분이 있으면 그 면을 찍어 주세요."
    else:
        shooting_tip = {
            "blurry": "카메라 화면에서 글자를 눌러 초점을 맞춘 뒤",
            "glare": "플래시를 끄고 빛이 비스듬히 들어오는 곳에서",
            "cropped": "라벨이 잘리지 않게 펼친 뒤",
        }.get(issue, "라벨을 평평하게 펼친 뒤")
        instructions = f"옷 안쪽 세탁 라벨에서 {symbols} 부분을 {shooting_tip} 가까이 찍어 주세요."
    return PhotoRequest(image_type="care_label", instructions=instructions)


def format_analysis(readings: PhotoReadings, requested_type: RequestedPhotoType) -> AnalysisResponse:
    image_type = readings.image_type
    if image_type == "unknown" or (requested_type != "auto" and requested_type != image_type):
        if requested_type == "care_label":
            photo_request = (
                request_label_photo(LabelReadings(), readings.photo_issue) if readings.photo_issue else None
            ) or new_label_photo_request()
        else:
            photo_request = PhotoRequest(
                image_type="garment",
                instructions="옷 한 벌을 밝은 곳에 펼쳐 목 부분부터 밑단까지 앞면 전체가 나오게 찍어 주세요.",
            )
        return AnalysisResponse(
            image_type="unknown",
            status="needs_confirmation",
            next_actions=["retake_photo", "manual_entry"],
            photo_request=photo_request,
            message=f"사진에서 확인하기 어려웠어요. {photo_request.instructions}",
        )

    if image_type == "garment":
        garment = readings.garment or GarmentReadings()
        fields = format_fields(garment)
        suggestion = readings.photo_care
        guidance = []
        if garment.garment_type and garment.color and suggestion and suggestion.sorting:
            guidance = [SORTING_GUIDANCE[suggestion.sorting]]
        photo_request = new_label_photo_request()
        return AnalysisResponse(
            image_type="garment",
            status="needs_confirmation",
            garment=fields,
            care_guidance=guidance,
            care_guidance_source="estimated" if guidance else None,
            photo_request=photo_request,
            next_actions=["capture_label", "manual_entry"],
            message=f"세탁·건조 방법을 확인하려면 라벨 사진이 필요해요. {photo_request.instructions}",
        )

    label = readings.care_label or LabelReadings()
    if label.wash_method and label.wash_method.value == "do_not_wash":
        label = label.model_copy(update={"max_wash_temperature_c": None, "wash_cycle": None})
    elif temperature := label.max_wash_temperature_c:
        evidence = normalize("NFKC", temperature.evidence).replace("−", "-")
        evidence_numbers = {
            Decimal(number.replace(",", "."))
            for number in re.findall(r"[+-]?\d+(?:[.,]\d+)?", evidence)
        }
        non_celsius = re.search(r"%|\d\s*°?\s*(?:F|Fahrenheit)\b|화씨", evidence, re.IGNORECASE)
        if evidence_numbers != {temperature.value} or non_celsius:
            label = label.model_copy(update={"max_wash_temperature_c": None})
    if not (label.tumble_dry_allowed and label.tumble_dry_allowed.value):
        label = label.model_copy(update={"tumble_dry_heat": None})

    photo_request = request_label_photo(label, readings.photo_issue)
    guidance = describe_care(label)
    return AnalysisResponse(
        image_type="care_label",
        status="needs_confirmation" if photo_request else "analyzed",
        care_label=format_fields(label),
        care_guidance=guidance,
        care_guidance_source="care_label" if guidance else None,
        photo_request=photo_request,
        next_actions=["capture_label", "manual_entry"] if photo_request else [],
        message=(
            photo_request.instructions if photo_request else "라벨에서 읽은 세탁·건조 방법이에요."
        ),
    )


def format_fields(
    readings: GarmentReadings | LabelReadings,
    *,
    source: Literal["garment_photo", "care_label", "official_product"] | None = None,
) -> dict[str, AnalyzedField]:
    from_label = isinstance(readings, LabelReadings)
    source = source or ("care_label" if from_label else "garment_photo")
    known_status = {"care_label": "read_from_label", "garment_photo": "estimated", "official_product": "verified"}[source]
    fields = {}
    for name in type(readings).model_fields:
        reading = getattr(readings, name)
        fields[name] = AnalyzedField(
            value=reading.value if reading else None,
            source=source,
            status=known_status if reading else "needs_confirmation",
            evidence=reading.evidence if reading else None,
        )
    return fields


def describe_care(label: LabelReadings, *, official_product: bool = False) -> list[str]:
    guidance = []
    if label.wash_method:
        guidance.append(WASH_GUIDANCE[label.wash_method.value])
    if label.max_wash_temperature_c:
        source = "공식 안내" if official_product else "라벨"
        guidance.append(f"{source}에 표시된 최대 세탁 온도는 {label.max_wash_temperature_c.value}°C예요.")
    if label.wash_cycle and label.wash_method and label.wash_method.value == "machine_wash":
        guidance.append(WASH_CYCLE_GUIDANCE[label.wash_cycle.value])

    if label.tumble_dry_allowed:
        if not label.tumble_dry_allowed.value:
            guidance.append("건조기를 사용하지 마세요.")
        elif label.tumble_dry_heat:
            guidance.append(DRYER_GUIDANCE[label.tumble_dry_heat.value])
        else:
            guidance.append("건조기를 사용할 수 있어요. 건조 온도는 라벨에서 확인해 주세요.")

    if label.natural_dry:
        guidance.append(NATURAL_DRY_GUIDANCE[label.natural_dry.value])
    if label.dry_in_shade and label.dry_in_shade.value:
        guidance.append("그늘에서 말리세요.")
    for reading in (label.bleach, label.ironing, label.professional_cleaning, label.special_instructions):
        if reading and reading.value not in guidance:
            guidance.append(reading.value)
    return guidance
