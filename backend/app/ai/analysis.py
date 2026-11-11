import re
from decimal import Decimal
from unicodedata import normalize

from .schemas import (
    AnalysisResponse,
    AnalyzedField,
    FieldSource,
    GarmentReadings,
    LabelReadings,
    MaterialCareTips,
    PhotoIssue,
    PhotoReadings,
    PhotoRequest,
    ProductSource,
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
MATERIAL_PREFIX = "소재 기준 권장: "
LEATHER_FIBERS = {"가죽", "스웨이드", "leather", "suede"}
WOOL_FIBERS = ("울", "모", "양모", "캐시미어", "메리노", "알파카", "앙고라", "wool", "cashmere", "merino")
DOWN_FIBERS = {"다운", "덕다운", "구스", "오리털", "거위털", "솜털", "깃털", "down", "feather", "feathers"}
# Use the most delicate listed fiber for products that already have a verified catalog entry.
MATERIAL_RULES = (
    (("실크", "견", "silk"),
     "마찰을 줄이고 중성세제를 사용하세요.", "직사광선을 피해 그늘에서 말리세요."),
    (WOOL_FIBERS,
     "울 전용 중성세제를 쓰고 비비지 마세요.", "비틀어 짜지 말고 평평하게 펴서 그늘에 말리세요."),
    (("레이온", "비스코스", "모달", "텐셀", "리오셀", "큐프라", "rayon", "viscose", "modal", "lyocell", "tencel"),
     "젖은 상태에서 세게 비비거나 비틀어 짜지 마세요.", "모양을 잡아 자연 건조하세요."),
    (("린넨", "리넨", "마", "linen"),
     "강하게 비비면 구김이 생길 수 있어요. 옷감에 가해지는 마찰을 줄여 주세요.", "모양을 잡아 자연 건조하세요."),
    (("아크릴", "acrylic"),
     "보풀이 생기기 쉬워 다른 옷과의 마찰을 줄여 주세요.", "모양을 잡아 자연 건조하세요."),
    (("면", "코튼", "cotton"),
     "면은 뜨거운 물에서 줄어들 수 있어요. 찬물이나 미지근한 물로 세탁하세요.",
     "모양을 잡아 자연 건조하세요."),
    (("나일론", "폴리아미드", "nylon", "polyamide"),
     "나일론은 열에 약해 뜨거운 물을 피하는 편이 좋아요.", "직사광선을 피해 자연 건조하세요."),
    (("폴리에스터", "폴리에스테르", "polyester"),
     "보풀을 줄이도록 다른 옷과의 마찰을 줄여 주세요.", "열이 닿지 않는 곳에서 자연 건조하세요."),
)
STRETCH_FIBERS = ("폴리우레탄", "스판덱스", "엘라스테인", "스판", "elastane", "spandex", "lycra")
WASHING_TIPS = {
    "mesh_bag": "세탁망에 넣어 다른 옷과의 마찰을 줄여 주세요.",
    "mild_detergent": "중성세제를 사용해 옷감의 부담을 줄여 주세요.",
    "wool_detergent": "울 전용 중성세제를 사용하세요.",
    "light_agitation": "세게 비비거나 비틀어 짜지 마세요.",
    "avoid_softener": "섬유유연제는 피하는 편이 좋아요.",
}
DRYING_TIPS = {
    "dry_flat": "늘어나지 않도록 모양을 잡아 평평하게 말리세요.",
    "dry_in_shade": "직사광선을 피해 그늘에서 말리세요.",
    "reshape_and_air_dry": "모양을 잡아 자연 건조하세요.",
}


# General habits for a kind of garment, shown when no label or published care is known.
# They never state a temperature, a cycle or a permission. The label decides those.
GARMENT_TIPS = (
    (r"가죽|레더|스웨이드|무스탕|leather|suede", False, (
        "가죽·스웨이드는 보통 물세탁하지 않아요. 전문 세탁에 맡기는 편이 안전해요.",
        "젖었을 때는 마른 천으로 눌러 닦고 그늘에서 말리세요.",
    )),
    (r"코트|블레이저|정장|수트|슈트|coat|blazer|suit", False, (
        "코트·정장류는 드라이클리닝만 가능한 경우가 많아요. 세탁 전에 라벨을 꼭 확인하세요.",
        "입은 뒤에는 옷걸이에 걸어 통풍시키고 먼지를 털어 주세요.",
    )),
    (r"니트|스웨터|가디건|카디건|knit|sweater|cardigan", True, (
        "니트는 줄거나 늘어나기 쉬워요. 보통 찬물에 중성세제로 손세탁하거나 세탁망에 넣어 약하게 세탁해요.",
        "비틀어 짜지 말고 평평하게 펴서 말리세요.",
    )),
    (r"청바지|데님|jean|denim", True, (
        "데님은 물이 빠질 수 있어요. 뒤집어서 비슷한 색끼리 찬물로 세탁하세요.",
        "건조기에서는 줄어들 수 있어 자연 건조가 안전해요.",
    )),
    (r"티셔츠|맨투맨|스웨트|스웻|후드|후디|hoodie|sweatshirt|t-shirt|\btee\b", True, (
        "프린트나 자수가 있으면 뒤집어서 세탁해야 덜 상해요.",
        "보통 비슷한 색끼리 찬물이나 미지근한 물로 세탁해요.",
        "건조기 고온에서는 줄어들 수 있어 자연 건조가 안전해요.",
    )),
    (r"셔츠|블라우스|shirt|blouse", True, (
        "단추를 잠그고 세탁망에 넣으면 형태가 덜 틀어져요.",
        "옷걸이에 걸어 말리면 구김이 줄어요.",
    )),
    (r"원피스|드레스|스커트|치마|dress|skirt", True, (
        "얇은 원단이나 장식이 있으면 세탁망에 넣어 약하게 세탁하는 편이 안전해요.",
        "옷걸이에 걸어 그늘에서 말리세요.",
    )),
    (r"트레이닝|조거|레깅스|운동|스포츠|기능성|바람막이|윈드|저지|track|jogger|legging", True, (
        "기능성 원단에는 섬유유연제를 피하는 편이 좋아요.",
        "건조기 고온은 원단을 상하게 할 수 있어 자연 건조가 안전해요.",
    )),
    (r"재킷|자켓|점퍼|집업|jacket|jumper", True, (
        "지퍼와 단추를 잠그고 뒤집어서 세탁하면 겉면이 덜 상해요.",
        "소재에 따라 물세탁이 안 될 수 있으니 라벨을 먼저 확인하세요.",
    )),
    (r"바지|팬츠|슬랙스|pants|trousers", True, (
        "뒤집어서 비슷한 색끼리 세탁하세요.",
        "주름을 잡은 바지는 옷걸이에 걸어 말리세요.",
    )),
)
PADDED_TIPS = (
    "패딩은 집에서 세탁하면 충전재가 뭉치거나 상하기 쉬워요. 전문 세탁에 맡기는 편이 안전해요.",
    "라벨에 물세탁 기호가 있을 때만 지퍼를 잠그고 중성세제로 단독 세탁하세요.",
    "섬유유연제와 표백제는 충전재를 상하게 할 수 있어 피하세요.",
    "보관할 때는 압축하지 말고 통풍이 되는 곳에 걸어 두세요.",
)


def is_padded_kind(description: str) -> bool:
    # A button-down shirt is not down-filled.
    text = normalize("NFKC", description).casefold()
    return is_padded_garment(text.replace("버튼다운", "").replace("button-down", ""))


def home_wash_unsuitable(description: str) -> bool:
    """Padded, leather and tailored garments are usually cleaned professionally, so a product search adds little."""
    text = normalize("NFKC", description).casefold()
    return is_padded_kind(text) or any(
        not washable and re.search(pattern, text) for pattern, washable, _ in GARMENT_TIPS
    )


def general_care_tips(description: str, color: str = "") -> list[str]:
    """Common care habits for the kind of garment. Empty when the kind is unknown."""
    text = normalize("NFKC", description).casefold().strip()
    if not text:
        return []
    if is_padded_kind(text):
        return list(PADDED_TIPS)
    washable, tips = next(
        ((washable, tips) for pattern, washable, tips in GARMENT_TIPS if re.search(pattern, text)),
        (True, ("보통 비슷한 색끼리 찬물이나 미지근한 물로 세탁해요.",)),
    )
    lines = list(tips)
    shade = normalize("NFKC", color).casefold()
    if washable and re.search(r"검정|검은|블랙|black|네이비|navy|남색|진청|빨강|레드|red|dark", shade):
        lines.append("진한 색은 물이 빠질 수 있어 처음 몇 번은 따로 세탁하세요.")
    elif washable and re.search(r"흰|화이트|white|아이보리|ivory|크림|cream", shade):
        lines.append("밝은 색 옷은 물들지 않게 밝은 색끼리 세탁하세요.")
    # The label request that accompanies these tips already tells the user to check the label.
    return lines


def is_padded_garment(description: str, fiber_content: str = "") -> bool:
    padded_terms = r"패딩|푸퍼|퍼퍼|다운|퀼팅|\b(?:puffer|padded|quilted|insulated)\b|\bdown\s+(?:jacket|coat|vest)\b"
    fill_terms = r"충전재|충전물|\b(?:fill|filling|insulation)\b"
    fibers = set(re.findall(r"[a-z]+|[가-힣]+", fiber_content.casefold()))
    return bool(
        fibers & DOWN_FIBERS
        or re.search(fill_terms, fiber_content, re.IGNORECASE)
        or re.search(padded_terms, description, re.IGNORECASE)
    )


def material_guidance(label: LabelReadings, tips: MaterialCareTips | None = None, *, padded: bool = False) -> list[str]:
    if label.fiber_content is None:
        return []
    method = label.wash_method.value if label.wash_method else None
    notes = " ".join(reading.value for reading in (label.professional_cleaning, label.special_instructions) if reading)
    no_water = r"물세탁(?:은|을)?\s*(?:금지|불가|피)|드라이\s*클리닝\s*(?:만|전용)|dry[ -]clean only|do not wash"
    if method == "do_not_wash" or re.search(no_water, notes, re.IGNORECASE):
        return []
    fibers = set(re.findall(r"[a-z]+|[가-힣]+", normalize("NFKC", label.fiber_content.value).casefold()))
    if fibers & LEATHER_FIBERS:
        return []
    if padded:
        # The shell and filling alone cannot establish home washing or drying permissions.
        if method in {"machine_wash", "hand_wash"} and fibers & DOWN_FIBERS and not re.search(
            r"세제|섬유유연제|detergent|softener", notes, re.IGNORECASE,
        ):
            return [f"{MATERIAL_PREFIX}다운 충전재에는 섬유유연제를 피하는 편이 좋아요."]
        return []
    _, washing, drying = next((rule for rule in MATERIAL_RULES if fibers & set(rule[0])), ((), None, None))
    if fibers & set(STRETCH_FIBERS):
        washing = washing or WASHING_TIPS["avoid_softener"]
        drying = drying or DRYING_TIPS["reshape_and_air_dry"]
    washing_tip = tips.washing if tips else None
    hand_wash_only = method == "hand_wash" or re.search(r"손세탁\s*만|hand[ -]wash only", notes, re.IGNORECASE)
    if (washing_tip == "mesh_bag" and hand_wash_only) or (
        washing_tip == "wool_detergent" and fibers.isdisjoint(WOOL_FIBERS)
    ):
        washing_tip = None
    if washing_tip:
        washing = WASHING_TIPS[washing_tip]
    if tips and tips.drying:
        drying = DRYING_TIPS[tips.drying]
    lines = []
    has_washing_details = label.max_wash_temperature_c is not None or label.wash_cycle is not None or re.search(
        r"세제|세탁망|섬유유연제|detergent|softener|mesh bag", notes, re.IGNORECASE,
    )
    if washing and not has_washing_details:
        permission = "세탁기 사용" if washing_tip == "mesh_bag" else "물세탁"
        lines.append(washing if method else f"라벨에서 {permission}을 허용하면 {washing}")
    drying_is_specified = any(field is not None for field in (
        label.natural_dry, label.tumble_dry_allowed, label.dry_in_shade,
    )) or re.search(r"건조|말리|(?:tumble|air|line) dry|dry flat", notes, re.IGNORECASE)
    if drying and not drying_is_specified:
        lines.append(drying)
    return [MATERIAL_PREFIX + line for line in lines]


def request_care_label_for_unmatched_product(result: AnalysisResponse) -> AnalysisResponse:
    kind = result.garment.get("garment_type")
    photo_request = new_label_photo_request(padded=is_padded_garment(str(kind.value or "")) if kind else False)
    message = result.search_warning or "같은 상품을 확인하지 못했어요."
    return result.model_copy(update={
        "photo_request": photo_request,
        "next_actions": ["capture_label", "manual_entry"],
        "message": f"{message} {photo_request.instructions}",
    })


def new_label_photo_request(*, padded: bool = False) -> PhotoRequest:
    return PhotoRequest(
        image_type="care_label",
        instructions=(
            "패딩 안쪽 라벨에서 물세탁·건조 기호와 충전재 표기가 보이도록 찍어 주세요."
            if padded else "정확한 세탁법은 옆 솔기나 목 뒤의 라벨을 찍어 확인해 주세요."
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
            photo_request = new_label_photo_request()
        return AnalysisResponse(
            image_type="unknown",
            status="needs_confirmation",
            next_actions=["capture_label", "manual_entry"],
            photo_request=photo_request,
            message=f"사진에서 확인하기 어려웠어요. {photo_request.instructions}",
        )

    if image_type == "garment":
        garment = readings.garment or GarmentReadings()
        fields = format_fields(garment)
        kind = garment.garment_type.value if garment.garment_type else ""
        photo_request = new_label_photo_request(padded=is_padded_garment(kind))
        tips = general_care_tips(kind, garment.color.value if garment.color else "")
        return AnalysisResponse(
            image_type="garment",
            status="needs_confirmation",
            garment=fields,
            care_guidance=tips,
            care_guidance_source="estimated" if tips else None,
            photo_request=photo_request,
            next_actions=["capture_label", "manual_entry"],
            message=f"세탁·건조 방법을 확인하려면 라벨 사진이 필요해요. {photo_request.instructions}",
        )

    label = normalize_care(readings.care_label or LabelReadings())
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
        message=label_message(label, guidance, photo_request),
    )


def normalize_care(label: LabelReadings) -> LabelReadings:
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
    return label


def label_message(label: LabelReadings, guidance: list[str], photo_request: PhotoRequest | None) -> str:
    sentences = list(guidance)
    if label.wash_method and label.max_wash_temperature_c:
        temperature = label.max_wash_temperature_c.value
        if label.wash_method.value == "machine_wash":
            cycle = {"normal": "표준", "gentle": "약한", "very_gentle": "아주 약한"}
            setting = cycle[label.wash_cycle.value] if label.wash_cycle else None
            washing = (
                f"세탁기에 넣을 땐 물 온도를 {temperature}°C 이하로 맞추고 {setting} 코스로 돌려 주세요."
                if setting else f"세탁기에 넣을 땐 {temperature}°C 이하의 물로 세탁해 주세요."
            )
            sentences[:3 if setting else 2] = [washing]
        elif label.wash_method.value == "hand_wash":
            sentences[:2] = [f"{temperature}°C 이하의 물에서 손세탁해 주세요."]
    if label.tumble_dry_allowed and not label.tumble_dry_allowed.value and label.natural_dry:
        index = sentences.index("건조기를 사용하지 마세요.")
        drying = NATURAL_DRY_GUIDANCE[label.natural_dry.value].removeprefix("옷을 ")
        sentences[index:index + 2] = [f"건조기 대신 {drying}"]
    sentences = ["표백제는 쓰지 마세요." if line == "표백 금지" else line for line in sentences]
    if photo_request:
        sentences.append(photo_request.instructions)
    return " ".join(sentences) or "라벨에서 읽은 세탁·건조 방법이에요."


def format_fields(
    readings: GarmentReadings | LabelReadings,
    *,
    source: FieldSource | None = None,
) -> dict[str, AnalyzedField]:
    from_label = isinstance(readings, LabelReadings)
    source = source or ("care_label" if from_label else "garment_photo")
    known_status = {"care_label": "read_from_label", "garment_photo": "estimated"}.get(source, "verified")
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


def describe_care(label: LabelReadings, *, product_source: ProductSource | None = None) -> list[str]:
    guidance = []
    if label.wash_method:
        guidance.append(WASH_GUIDANCE[label.wash_method.value])
    if label.max_wash_temperature_c:
        source = {"official_product": "공식 안내", "product_listing": "판매처 상품 안내"}.get(product_source, "라벨")
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
