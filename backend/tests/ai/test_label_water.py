from backend.app.ai.analysis import describe_care, format_analysis, label_message, normalize_care
from backend.app.ai.schemas import LabelReadings, PhotoReadings

PREFIX = "소재 기준 권장: "


def read(**fields):
    care = {name: {"value": value, "evidence": str(value)} for name, value in fields.items()}
    return format_analysis(
        PhotoReadings.model_validate({"image_type": "care_label", "care_label": care}), "care_label",
    )


def material(result):
    return [line for line in result.care_guidance if line.startswith(PREFIX)]


def label_lines(result):
    return [line for line in result.care_guidance if not line.startswith(PREFIX)]


def test_worded_water_reading_is_guidance_and_field_and_suppresses_request_and_fibre_tip():
    result = read(
        wash_method="machine_wash", wash_water="찬물로 세탁하세요.", fiber_content="면 100%",
    )
    assert result.care_guidance[:2] == ["세탁기로 세탁할 수 있어요.", "찬물로 세탁하세요."] or (
        result.care_guidance[1] == "찬물로 세탁하세요."
    )
    assert result.care_label["wash_water"].value == "찬물로 세탁하세요."
    assert result.care_label["wash_water"].status == "read_from_label"
    assert not any("물 온도 · " in line for line in material(result))
    assert not result.photo_request or "숫자" not in result.photo_request.instructions
    assert "찬물로 세탁하세요." in result.message


def test_water_phrase_keeps_prohibition_verbatim():
    result = read(wash_method="machine_wash", wash_water="뜨거운 물은 사용하지 마세요.")
    assert "뜨거운 물은 사용하지 마세요." in result.care_guidance


def test_hand_wash_label_with_fibres_gets_prefixed_water_tip_after_label_lines():
    result = read(wash_method="hand_wash", fiber_content="울 100%")
    tips = material(result)
    assert any(line.startswith(f"{PREFIX}물 온도 · ") for line in tips)
    assert result.care_guidance[: len(label_lines(result))] == label_lines(result)
    assert result.care_guidance.index(tips[0]) >= len(label_lines(result))
    assert result.care_guidance_source == "care_label"


def test_numeric_temperature_suppresses_fibre_water_tip():
    result = read(wash_method="machine_wash", max_wash_temperature_c=30, fiber_content="면 100%")
    assert not any("물 온도 · " in line for line in material(result))
    assert any("30°C" in line for line in label_lines(result))


def test_do_not_wash_gets_no_material_tips_and_drops_water():
    result = read(wash_method="do_not_wash", wash_water="찬물로 세탁하세요.", fiber_content="면 100%")
    assert material(result) == []
    assert result.care_label["wash_water"].value is None
    assert "찬물로 세탁하세요." not in result.care_guidance
    assert normalize_care(LabelReadings.model_validate({
        "wash_method": {"value": "do_not_wash", "evidence": "x"},
        "wash_water": {"value": "찬물로 세탁하세요.", "evidence": "x"},
    })).wash_water is None


def test_fibres_only_label_uses_material_estimate_source():
    result = read(fiber_content="면 100%")
    assert label_lines(result) == []
    assert material(result)
    assert result.care_guidance_source == "material_estimate"


def test_label_message_ignores_material_lines():
    result = read(wash_method="machine_wash", max_wash_temperature_c=30, fiber_content="면 100%")
    assert "소재 기준" not in result.message
    assert "30°C 이하의 물로 세탁해 주세요." in result.message


def test_label_message_rewrite_survives_the_water_sentence():
    label = LabelReadings.model_validate({
        "wash_method": {"value": "machine_wash", "evidence": "x"},
        "wash_water": {"value": "찬물로 세탁하세요.", "evidence": "x"},
        "max_wash_temperature_c": {"value": 30, "evidence": "30"},
        "wash_cycle": {"value": "gentle", "evidence": "x"},
        "tumble_dry_allowed": {"value": False, "evidence": "x"},
    })
    message = label_message(label, describe_care(label), None)
    assert message.startswith("세탁기에 넣을 땐 물 온도를 30°C 이하로 맞추고 약한 코스로 돌려 주세요. 찬물로 세탁하세요.")
    assert "건조기를 사용하지 마세요." in message
    assert "최대 세탁 온도" not in message


def test_label_message_hand_wash_with_water_sentence():
    label = LabelReadings.model_validate({
        "wash_method": {"value": "hand_wash", "evidence": "x"},
        "wash_water": {"value": "미지근한 물로 세탁하세요.", "evidence": "x"},
        "max_wash_temperature_c": {"value": 30, "evidence": "30"},
    })
    message = label_message(label, describe_care(label), None)
    assert message == "30°C 이하의 물에서 손세탁해 주세요. 미지근한 물로 세탁하세요."
