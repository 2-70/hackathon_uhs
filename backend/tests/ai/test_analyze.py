import base64
import json
from hashlib import sha256
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from pydantic import HttpUrl

from backend.app.ai import catalog, catalog_photo, official_product
from backend.app.ai import router as image_router
from backend.app.ai.gemini import GeminiAnalyzer
from backend.app.ai.lens import LensWebSearch
from backend.app.ai.preview import app
from backend.app.ai.product_page import ProductPage
from backend.app.ai.router import get_analyzer, get_lens_search, get_web_search
from backend.app.ai.schemas import PhotoReadings
from backend.app.ai.web_search import VisionWebSearch


@pytest.fixture
def photo():
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_VISION_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)

    async def no_product_page(*_):
        return None

    async def no_candidate_photos(*_):
        return {}

    monkeypatch.setattr(official_product, "read_product_page", no_product_page)
    monkeypatch.setattr(official_product, "read_candidate_photos", no_candidate_photos)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def answer_single_request(handler):
    """Answer a combined photo-and-product request with the test's photo reply and product reply."""

    def respond(request):
        payload = json.loads(request.content)
        config = payload["generationConfig"]
        if "photo" not in config["responseJsonSchema"].get("properties", {}):
            return handler(request)
        GEMINI_REQUESTS.append("combined")
        requested, *lookup = payload["contents"][0]["parts"]

        def ask(parts, instruction, schema, tools):
            body = {
                **{key: value for key, value in payload.items() if key != "tools"}, **tools,
                "contents": [{"parts": parts}], "systemInstruction": {"parts": [{"text": instruction}]},
                "generationConfig": {**config, "responseJsonSchema": schema},
            }
            return handler(httpx.Request("POST", request.url, headers={"x-goog-api-key": "test-key"}, json=body))

        photo = ask([requested, lookup[1]], "Read one photo", PhotoReadings.model_json_schema(), {})
        if photo.status_code != 200:
            return photo
        product = ask(
            lookup, official_product.VERIFY_INSTRUCTION, official_product.OfficialReading.model_json_schema(),
            {"tools": payload["tools"]} if "tools" in payload else {},
        )
        if product.status_code != 200:
            return product
        reply = product.json()
        product_text = reply["candidates"][0]["content"]["parts"][0]["text"]
        photo_text = photo.json()["candidates"][0]["content"]["parts"][0]["text"]
        product_reading = json.loads(product_text)
        if "image_type" in product_reading:
            # The test answers every request with a photo reading, so no product was identified.
            product_reading = {}
        reply["candidates"][0]["content"]["parts"][0]["text"] = json.dumps(
            {"photo": json.loads(photo_text), "product": product_reading},
        )
        return httpx.Response(200, json=reply)

    return respond


GEMINI_REQUESTS: list[str] = []


def mock_gemini(handler):
    GEMINI_REQUESTS.clear()
    analyzer = GeminiAnalyzer(api_key="test-key", transport=httpx.MockTransport(answer_single_request(handler)))
    app.dependency_overrides[get_analyzer] = lambda: analyzer


def gemini_result(readings):
    return httpx.Response(200, json={"candidates": [{
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(readings)}]},
    }]})


def test_reads_label_and_explains_washing_and_drying(client, photo):
    def handler(request):
        assert request.url.path.endswith(":generateContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        payload = json.loads(request.content)
        parts = payload["contents"][0]["parts"]
        assert parts[0]["text"].endswith("care_label")
        assert parts[1]["inlineData"]["mimeType"] == "image/jpeg"
        assert base64.b64decode(parts[1]["inlineData"]["data"]) == photo
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert "care_label" in schema["properties"] and "garment" not in schema["properties"]
        return gemini_result({"image_type": "care_label", "care_label": {
            "fiber_content": {"value": "면 100%", "evidence": "100% COTTON"},
            "wash_method": {"value": "machine_wash", "evidence": "세탁통 기호"},
            "max_wash_temperature_c": {"value": 30, "evidence": "세탁통 안 숫자 30"},
            "bleach": {"value": "표백 금지", "evidence": "DO NOT BLEACH"},
            "tumble_dry_allowed": {"value": False, "evidence": "건조기 기호 위 X"},
        }})

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)}, data={"image_type": "care_label"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "analyzed"
    assert result["care_label"]["fiber_content"] == {
        "value": "면 100%", "source": "care_label", "status": "read_from_label", "evidence": "100% COTTON",
    }
    assert result["care_label"]["tumble_dry_allowed"]["value"] is False
    assert "라벨에 표시된 최대 세탁 온도는 30°C예요." in result["care_guidance"]
    assert "건조기를 사용하지 마세요." in result["care_guidance"]
    assert "표백 금지" in result["care_guidance"]
    assert result["care_guidance_source"] == "care_label"
    assert result["photo_request"] is None
    assert result["message"] == (
        "세탁기에 넣을 땐 30°C 이하의 물로 세탁해 주세요. 건조기를 사용하지 마세요. 표백제는 쓰지 마세요."
    )


def test_exact_label_reupload_reuses_readings_without_crossing_photo_types(client, photo):
    requested_types = []

    def handler(request):
        parts = json.loads(request.content)["contents"][0]["parts"]
        requested_types.append(parts[0]["text"].split()[-1])
        if requested_types[-1] == "garment":
            return gemini_result({"image_type": "unknown"})
        return gemini_result({"image_type": "care_label", "care_label": {
            "wash_method": {"value": "hand_wash", "evidence": "HAND WASH"},
            "max_wash_temperature_c": {"value": 30, "evidence": "MAX 30°C"},
            "tumble_dry_allowed": {"value": False, "evidence": "DO NOT TUMBLE DRY"},
        }})

    mock_gemini(handler)
    first = client.post("/api/analyze", files={"image": ("first.jpg", photo)}, data={"image_type": "care_label"})
    repeated = client.post("/api/analyze", files={"image": ("repeat.jpg", photo)}, data={"image_type": "care_label"})
    other_type = client.post("/api/analyze", files={"image": ("repeat.jpg", photo)}, data={"image_type": "garment"})

    assert first.status_code == repeated.status_code == 200
    assert first.json()["status"] == "analyzed"
    assert first.json() == repeated.json()
    assert other_type.json()["image_type"] == "unknown"
    assert requested_types == ["care_label", "garment"]


@pytest.mark.parametrize(("kind", "searched"), [("롱패딩", False), ("가죽 재킷", False), ("울 코트", False), ("후드 티셔츠", True)])
def test_garments_not_washed_at_home_get_no_product_lookup(client, photo, kind, searched):
    searches = []
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "garment_type": {"value": kind, "evidence": "옷의 형태"},
    }}))

    def lens(request):
        searches.append(request.url.params.get("engine"))
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        return httpx.Response(200, json={request.url.params.get("type", "organic_results"): []})

    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(lens))
    result = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}).json()

    # The image search runs before the single model request. Text searches for a product do not.
    assert not any("google" == engine for engine in searches)
    assert result["care_guidance_source"] == "estimated"
    assert result["photo_request"]["image_type"] == "care_label"
    if searched:
        assert result["product_lookup"]["status"] == "not_found"
    else:
        # The kind of garment alone decides this, so no product lookup is reported.
        assert result["product_lookup"] is None
        assert "전문 세탁" in result["message"] and kind in result["message"]
        assert any("전문 세탁" in line or "드라이클리닝" in line for line in result["care_guidance"])


def test_unmatched_padded_garment_requests_label_without_estimated_care(client, photo):
    suggestion = {
        "sorting": "separate_dark_colors",
        "handling": "print_or_embroidery",
        "washing": "30°C로 세탁하세요.",
        "drying": "건조기를 쓰세요.",
    }

    def handler(request):
        payload = json.loads(request.content)
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert "photo_issue" in schema["properties"]
        assert set(schema["$defs"]["PhotoCareSuggestion"]["properties"]) == {"sorting", "handling", "guidance"}
        return gemini_result({"image_type": "garment", "garment": {
            "garment_type": {"value": "패딩", "evidence": "부풀어 오른 퀼팅 외투"},
            "color": {"value": "다크 그레이", "evidence": "짙은 회색"},
            "product_code": {"value": "ABC-123", "evidence": "옷에 ABC-123이라고 인쇄됨"},
        }, "photo_care": suggestion})

    mock_gemini(handler)
    first = client.post("/api/analyze", files={"image": ("shirt.jpg", photo)}).json()
    assert first["photo_request"]["image_type"] == "care_label"
    assert "충전재" in first["photo_request"]["instructions"]
    # General habits for padded outerwear are shown. Wash settings suggested from appearance are not.
    assert first["care_guidance_source"] == "estimated"
    assert "전문 세탁" in first["care_guidance"][0]
    assert not any("30" in line or "건조기를 쓰세요" in line for line in first["care_guidance"])
    response = client.post(
        "/api/analyze", files={"image": ("shirt.jpg", photo)}, data={"search_stage": "retry"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["image_type"] == "garment"
    assert result["status"] == "needs_confirmation"
    assert result["garment"]["product_code"]["value"] == "ABC-123"
    assert result["garment"]["product_code"]["status"] == "estimated"
    assert result["garment"]["brand"]["status"] == "needs_confirmation"
    assert result["care_guidance_source"] == "estimated"
    assert result["care_guidance"] == first["care_guidance"]
    assert result["product_care"] == {}
    # A padded garment is not searched again, so no tag photo is requested.
    assert result["next_actions"] == ["capture_label", "manual_entry"]
    assert result["photo_request"]["image_type"] == "care_label"
    assert "충전재" in result["photo_request"]["instructions"]

    search = LensWebSearch("test-key", httpx.MockTransport(lambda _: pytest.fail("Unexpected web search")))
    app.dependency_overrides[get_lens_search] = lambda: search
    estimate = client.post(
        "/api/analyze", files={"image": ("shirt.jpg", photo)}, data={"search_stage": "estimate"},
    ).json()
    assert estimate["care_guidance"] == result["care_guidance"]
    assert estimate["product_lookup"] is None


def test_unconfirmed_product_requests_a_label_and_uses_it_for_care(client, photo):
    def handler(request):
        parts = json.loads(request.content)["contents"][0]["parts"]
        if parts[0]["text"].endswith("care_label"):
            return gemini_result({"image_type": "care_label", "care_label": {
                "wash_method": {"value": "machine_wash", "evidence": "MACHINE WASH"},
                "max_wash_temperature_c": {"value": 30, "evidence": "MAX 30°C"},
                "tumble_dry_allowed": {"value": False, "evidence": "DO NOT TUMBLE DRY"},
            }})
        return gemini_result({"image_type": "garment", "garment": {
            "brand": {"value": "나이키", "evidence": "스우시"},
            "garment_type": {"value": "맨투맨", "evidence": "긴소매와 둥근 목"},
            "product_code": {"value": "IX1937-001", "evidence": "외관이 비슷함"},
        }})

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("photo.jpg", photo)})
    assert response.status_code == 200
    data = response.json()
    assert data["product_lookup"]["status"] == "not_found"
    assert data["product_lookup"]["candidates"] == []
    assert data["product_care"] == {}
    assert data["photo_request"]["image_type"] == "care_label"
    assert "capture_label" in data["next_actions"]

    label = client.post(
        "/api/analyze", files={"image": ("label.jpg", photo)},
        data={"image_type": "care_label"},
    )
    assert label.status_code == 200
    assert label.json()["care_guidance_source"] == "care_label"
    assert label.json()["care_label"]["max_wash_temperature_c"]["value"] == 30
    assert "건조기를 사용하지 마세요." in label.json()["care_guidance"]


def test_advice_requires_a_recognizable_garment_type(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "photo_care": {
        "washing": "찬물에 세탁하세요.", "drying": "그늘에서 말리세요.",
    }}))
    response = client.post("/api/analyze", files={"image": ("unclear.jpg", photo)})

    assert response.status_code == 200
    result = response.json()
    assert result["care_guidance_source"] is None
    assert result["care_guidance"] == []


def test_phone_mpo_upload_sends_only_the_upright_primary_photo(client):
    upload = BytesIO()
    primary = Image.new("RGB", (12, 8), "red")
    auxiliary = Image.new("RGB", (12, 8), "blue")
    exif = Image.Exif()
    exif[274] = 6
    primary.save(upload, format="MPO", save_all=True, append_images=[auxiliary], exif=exif)

    def handler(request):
        inline_image = json.loads(request.content)["contents"][0]["parts"][1]["inlineData"]
        assert inline_image["mimeType"] == "image/jpeg"
        with Image.open(BytesIO(base64.b64decode(inline_image["data"]))) as image:
            assert image.format == "JPEG"
            assert image.size == (8, 12)
            assert image.getpixel((0, 0))[0] > 240
            assert image.getexif().get(274) is None
        return gemini_result({"image_type": "garment"})

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("phone.jpg", upload.getvalue(), "image/jpeg")})
    assert response.status_code == 200
    assert response.json()["image_type"] == "garment"


def test_large_png_is_resized_and_sent_as_jpeg(client, monkeypatch):
    monkeypatch.setattr(image_router, "MAX_INLINE_IMAGE_BYTES", 1024)
    monkeypatch.setattr(image_router, "MAX_COMPRESSED_IMAGE_EDGE", 24)
    upload = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("test", "x" * 2048)
    Image.new("RGBA", (16, 48), (0, 0, 0, 0)).save(upload, format="PNG", pnginfo=metadata)

    def handler(request):
        inline_image = json.loads(request.content)["contents"][0]["parts"][1]["inlineData"]
        assert inline_image["mimeType"] == "image/jpeg"
        with Image.open(BytesIO(base64.b64decode(inline_image["data"]))) as image:
            assert image.format == "JPEG"
            assert image.size == (8, 24)
            assert image.getpixel((0, 0)) == (255, 255, 255)
        return gemini_result({"image_type": "garment"})

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("large.png", upload.getvalue(), "image/png")})
    assert response.status_code == 200


def test_blurry_label_does_not_supply_unknown_settings(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "care_label", "care_label": {
        "fiber_content": {"value": "면 100%", "evidence": "100% COTTON"},
    }, "photo_issue": "blurry"}))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "needs_confirmation"
    assert result["care_label"]["max_wash_temperature_c"]["value"] is None
    assert result["care_label"]["max_wash_temperature_c"]["status"] == "needs_confirmation"
    # Only fibre-based tips remain; nothing is attributed to the label itself.
    assert all(line.startswith("소재 기준 권장: ") for line in result["care_guidance"])
    assert result["care_guidance_source"] == "material_estimate"
    assert "capture_label" in result["next_actions"]
    assert "초점을 맞춘 뒤" in result["photo_request"]["instructions"]


@pytest.mark.parametrize(("issue", "tip"), [
    ("cropped", "라벨이 잘리지 않게"),
    ("glare", "플래시를 끄고"),
    ("missing_information", "태그 뒷면"),
])
def test_partial_label_requests_only_missing_drying_details(client, photo, issue, tip):
    mock_gemini(lambda _: gemini_result({"image_type": "care_label", "photo_issue": issue, "care_label": {
        "wash_method": {"value": "machine_wash", "evidence": "세탁통 기호"},
        "max_wash_temperature_c": {"value": 30, "evidence": "세탁통 안 숫자 30"},
    }}))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert "라벨에 표시된 최대 세탁 온도는 30°C예요." in result["care_guidance"]
    assert result["care_label"]["tumble_dry_allowed"]["value"] is None
    instructions = result["photo_request"]["instructions"]
    assert "건조 기호" in instructions and tip in instructions
    assert "세탁 기호" not in instructions


def test_prohibitions_take_precedence_over_conflicting_settings(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "care_label", "care_label": {
        "wash_method": {"value": "do_not_wash", "evidence": "세탁통 기호 위 X"},
        "max_wash_temperature_c": {"value": 30, "evidence": "숫자 30"},
        "tumble_dry_allowed": {"value": False, "evidence": "건조기 기호 위 X"},
        "tumble_dry_heat": {"value": "low", "evidence": "점 하나"},
    }}))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["care_label"]["max_wash_temperature_c"]["value"] is None
    assert result["care_label"]["tumble_dry_heat"]["value"] is None
    assert result["care_guidance"] == ["물세탁을 피하세요.", "건조기를 사용하지 마세요."]


@pytest.mark.parametrize(("value", "evidence"), [
    (60, "MAX 30 C"),
    (30, "30℉"),
    (30, "30% COTTON"),
    (30, "MAX 30.5°C"),
])
def test_temperature_with_conflicting_evidence_is_withheld(client, photo, value, evidence):
    mock_gemini(lambda _: gemini_result({"image_type": "care_label", "care_label": {
        "wash_method": {"value": "machine_wash", "evidence": "MACHINE WASH"},
        "max_wash_temperature_c": {"value": value, "evidence": evidence},
        "tumble_dry_allowed": {"value": False, "evidence": "DO NOT TUMBLE DRY"},
    }}))

    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["care_label"]["max_wash_temperature_c"]["value"] is None
    assert result["care_guidance"] == ["세탁기로 세탁할 수 있어요.", "건조기를 사용하지 마세요."]
    assert "세탁 기호" in result["photo_request"]["instructions"]


def test_unrelated_photo_requests_a_care_label(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "unknown"}))
    response = client.post("/api/analyze", files={"image": ("other.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["next_actions"] == ["capture_label", "manual_entry"]
    assert result["photo_request"]["image_type"] == "care_label"


def test_non_image_is_rejected_before_calling_gemini(client):
    def handler(_):
        pytest.fail("An invalid image should not be sent to Gemini")

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("invalid.jpg", b"not a photo", "image/jpeg")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_image"


def test_invalid_model_values_do_not_become_care_guidance(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "care_label", "care_label": {
        "max_wash_temperature_c": {"value": 300, "evidence": "300"},
    }}))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_analysis_response"


def test_gemini_failure_returns_a_retryable_error(client, photo):
    mock_gemini(lambda _: httpx.Response(500, text="upstream debug details"))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "analysis_failed"
    assert "upstream debug details" not in response.text


@pytest.mark.parametrize(("status", "reason", "provider_message", "expected_code"), [
    (400, "API_KEY_INVALID", "Internal project information", "analysis_key_invalid"),
    (403, "API_KEY_SERVICE_BLOCKED", "Internal project information", "analysis_key_restricted"),
    (403, "", "Your API key was reported as leaked. Internal project information", "analysis_key_leaked"),
    (403, "", "Internal project information", "analysis_access_denied"),
    (429, "", "Internal project information", "analysis_busy"),
])
def test_gemini_errors_distinguish_access_from_quota(client, photo, status, reason, provider_message, expected_code):
    mock_gemini(lambda _: httpx.Response(status, json={"error": {
        "message": provider_message,
        "details": [{"reason": reason}],
    }}))
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == expected_code
    assert "Internal project information" not in response.text


def test_missing_key_reports_configuration_error(client, photo, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/api/analyze", files={"image": ("label.jpg", photo)})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analysis_unconfigured"


def test_registered_reference_photo_returns_official_care_without_gemini(client, photo, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    product = catalog.load_catalog()[0].model_copy(update={"image_sha256": [sha256(photo).hexdigest()]})
    monkeypatch.setattr(catalog, "load_catalog", lambda: [product])

    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})

    assert response.status_code == 200
    result = response.json()
    assert result["product_lookup"]["status"] == "matched"
    assert result["product_lookup"]["match_method"] == "reference_photo"
    assert result["product_lookup"]["product"]["source_url"].startswith("https://www.coor.kr/")
    assert result["product_care"]["wash_method"]["source"] == "official_product"
    assert result["product_care"]["tumble_dry_allowed"]["status"] == "needs_confirmation"
    assert result["care_guidance"][:3] == [
        "손세탁하세요.", "드라이클리닝도 가능해요.", "뒤집어서 세탁하는 방법은 권장하지 않아요.",
    ]
    material_guidance = result["care_guidance"][3:]
    assert all(line.startswith("소재 기준 권장: ") and " · " in line for line in material_guidance)
    assert any("물 온도 · " in line and "줄어들 수" in line for line in material_guidance)
    assert any("세제 · " in line and "중성세제" in line for line in material_guidance)
    assert any("건조 · " in line and "자연 건조" in line for line in material_guidance)
    assert "소재 기준의 잠정 권장 사항" in result["message"]
    assert result["care_guidance_source"] == "official_product"
    assert "건조 기호" in result["photo_request"]["instructions"]


def test_printed_brand_and_code_match_a_verified_product(client, photo, monkeypatch):
    entry = catalog.load_catalog()[0]
    entry = entry.model_copy(update={"product": entry.product.model_copy(update={"product_code": "CW-123"})})
    monkeypatch.setattr(catalog, "load_catalog", lambda: [entry])
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "brand": {"value": "coor", "evidence": "COOR 라벨"},
        "garment_type": {"value": "후디", "evidence": "후드와 긴 소매"},
        "product_code": {"value": "CW-123", "evidence": "품번 CW-123 표기"},
    }, "photo_care": {
        "washing": "라벨이 허용하면 찬물 약한 코스로 세탁하세요.", "drying": "그늘에서 말리세요.",
    }}))

    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})

    assert response.status_code == 200
    assert response.json()["product_lookup"]["match_method"] == "product_code"
    assert response.json()["care_guidance_source"] == "official_product"
    assert response.json()["care_guidance"][0] == "손세탁하세요."


@pytest.mark.parametrize("exact", [True, False])
def test_web_search_requires_a_catalog_reference_to_attach_care(client, photo, exact):
    entry = catalog.load_catalog()[0]
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "brand": {"value": "COOR", "evidence": "COOR 라벨"},
        "garment_type": {"value": "후디", "evidence": "후드와 긴 소매"},
    }}))

    def handler(request):
        payload = json.loads(request.content)["requests"][0]
        assert payload["features"][0]["type"] == "WEB_DETECTION"
        assert base64.b64decode(payload["image"]["content"]) == photo
        image_field = "fullMatchingImages" if exact else "partialMatchingImages"
        return httpx.Response(200, json={"responses": [{"webDetection": {"pagesWithMatchingImages": [{
            "url": str(entry.reference_page_url),
            "pageTitle": "<b>쿠어</b> 후디",
            image_field: [{"url": str(entry.reference_image_url) + "?format=webp&width=300"}],
        }]}}]})

    search = VisionWebSearch("test-key", transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_web_search] = lambda: search
    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})

    assert response.status_code == 200
    result = response.json()
    if exact:
        assert result["product_lookup"]["match_method"] == "web_image"
        assert result["care_guidance_source"] == "official_product"
    else:
        assert result["product_lookup"]["status"] == "not_found"
        assert result["product_lookup"]["candidates"] == []
        assert result["care_guidance_source"] == "estimated"
        assert result["product_care"] == {}
        assert result["photo_request"]["image_type"] == "care_label"


def test_web_search_failure_preserves_garment_analysis(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "brand": {"value": "COOR", "evidence": "COOR 라벨"},
    }}))
    search = VisionWebSearch("test-key", transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    app.dependency_overrides[get_web_search] = lambda: search

    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})

    assert response.status_code == 200
    assert response.json()["garment"]["brand"]["value"] == "COOR"
    assert response.json()["product_lookup"]["status"] == "search_unavailable"


def test_lens_returns_ranked_candidates_without_a_catalog(client, photo, monkeypatch, caplog):
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "brand": {"value": "Nike", "evidence": "스우시 로고"},
    }}))
    app.dependency_overrides[catalog.get_catalog] = lambda: None
    requests = []
    matches = [
        {"title": "", "link": "https://example.com/untitled"},
        {"title": "Invalid link", "link": "javascript:alert(1)"},
        {"title": "Embedded credentials", "link": "https://a:b@example.com/item"},
        {"title": "Nike printed crew-neck", "link": "https://example.com/nike-crew"},
        {"title": "Duplicate", "link": "https://example.com/nike-crew"},
        *[{"title": f"Result {i}", "link": f"https://example.com/items/{i}"} for i in range(6)],
    ]

    def handler(request):
        if request.url.params.get("engine") == "google":
            assert any(term in request.url.params["q"] for term in ("site:nike.com", '"care instructions"'))
            return httpx.Response(200, json={"organic_results": []})
        requests.append((request.method, request.url.path, request.url.params.get("type")))
        assert request.url.host == "serpapi.com"
        if request.method == "POST":
            assert request.headers["content-type"].startswith("multipart/form-data;")
            assert b'name="image"; filename="garment.jpg"' in request.content
            assert b"image/jpeg" in request.content
            assert b"lens-test-key" in request.content
            return httpx.Response(200, json={"image_id": "test-upload-id"})
        assert request.url.params["api_key"] == "lens-test-key"
        assert request.url.params["image_id"] == "test-upload-id"
        assert request.url.params["engine"] == "google_lens"
        if request.url.params["type"] == "exact_matches":
            return httpx.Response(200, json={"exact_matches": []})
        assert request.url.params["type"] == "visual_matches"
        assert request.url.params["auto_crop"] == "true"
        return httpx.Response(200, json={"visual_matches": matches})

    monkeypatch.setenv("SERPAPI_API_KEY", "lens-test-key")
    monkeypatch.setattr(
        image_router, "LensWebSearch", lambda key: LensWebSearch(key, httpx.MockTransport(handler)),
    )
    with caplog.at_level("INFO", logger="httpx"):
        response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})

    assert requests[0] == ("POST", "/image", None)
    assert sorted(requests[1:]) == [
        ("GET", "/search.json", "exact_matches"), ("GET", "/search.json", "visual_matches"),
    ]
    assert "serpapi.com/search.json" in caplog.text
    assert "lens-test-key" not in caplog.text and "test-upload-id" not in caplog.text
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "needs_confirmation"
    lookup = result["product_lookup"]
    assert lookup["status"] == "candidates"
    assert lookup["product"] is None
    assert [item["name"] for item in lookup["candidates"]] == [
        "Nike printed crew-neck", "Result 0", "Result 1", "Result 2", "Result 3",
    ]
    assert lookup["candidates"][0]["source_url"] == "https://example.com/nike-crew"
    assert result["product_care"] == {}
    assert result["photo_request"]["image_type"] == "care_label"


@pytest.mark.parametrize(("search_response", "expected"), [
    ({"search_metadata": {"status": "Success"}, "error": "No results"}, "not_found"),
    ({"search_metadata": {"status": "Error"}, "error": "Search failed"}, "search_unavailable"),
])
def test_lens_preserves_photo_analysis_when_no_matches(client, photo, search_response, expected):
    mock_gemini(lambda _: gemini_result({"image_type": "garment", "garment": {
        "brand": {"value": "Nike", "evidence": "스우시 로고"},
    }}))

    def handler(request):
        payload = {"image_id": "test-id"} if request.method == "POST" else search_response
        return httpx.Response(200, json=payload)

    search = LensWebSearch("test-key", httpx.MockTransport(handler))
    app.dependency_overrides[get_lens_search] = lambda: search
    result = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}).json()

    assert result["garment"]["brand"]["value"] == "Nike"
    assert result["product_lookup"]["status"] == expected
    assert result["photo_request"]["image_type"] == "care_label"


def test_lens_does_not_search_before_gemini_reads_the_garment(client, photo):
    app.dependency_overrides[get_analyzer] = lambda: GeminiAnalyzer(api_key=None)

    def handler(_):
        pytest.fail("Gemini did not read the garment, so the product search must not start")

    search = LensWebSearch("test-key", httpx.MockTransport(handler))
    app.dependency_overrides[get_lens_search] = lambda: search
    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}, data={"image_type": "garment"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analysis_unconfigured"


@pytest.mark.parametrize("image_retrieved", [True, False])
@pytest.mark.parametrize("retailer_candidate", [True, False])
def test_lens_matches_an_uncatalogued_garment_using_retrieved_official_evidence(
    client, photo, image_retrieved, retailer_candidate,
):
    page = "https://www.nike.com/kr/t/sweatshirt/XX1234-001"
    retailer = "https://example.com/products/XX1234-001"
    reference = "https://static.nike.com/product-reference.jpg"
    def empty_catalog():
        return []

    app.dependency_overrides[catalog.get_catalog] = empty_catalog

    def analyze(request):
        payload = json.loads(request.content)
        if "tools" not in payload:
            return gemini_result({"image_type": "garment", "garment": {
                "brand": {"value": "나이키", "evidence": "스우시"},
            }})
        assert payload["tools"] == [{"url_context": {}}]
        context = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert context["references"][0]["page_url"] == page
        reading = gemini_result({
            "reference": 0, "match": "visual", "name": "나이키 프린트 스웻셔츠",
            "color": "Dark Grey", "product_code": "XX1234-001",
            **({"candidate_index": 0, "retailer_product_code": "XX1234-001"} if retailer_candidate else {}),
            "visual_evidence": ["가슴의 반복 인쇄 패턴", "밑단 옆에 달린 직사각형 패치"],
            "care": {
                "wash_method": {"value": "machine_wash", "evidence": "Machine wash at 30°C"},
                "max_wash_temperature_c": {"value": 30, "evidence": "Machine wash at 30°C"},
                "tumble_dry_allowed": {"value": False, "evidence": "Do not tumble dry"},
            },
        }).json()
        retrieved = [page, retailer] if retailer_candidate else [page]
        if image_retrieved:
            retrieved.append(reference)
        reading["candidates"][0]["urlContextMetadata"] = {"urlMetadata": [
            {"retrievedUrl": url, "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"}
            for url in retrieved
        ]}
        return httpx.Response(200, json=reading)

    def lens(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            if '"care instructions"' in request.url.params["q"]:
                return httpx.Response(200, json={"organic_results": []})
            assert retailer_candidate and request.url.params["q"] == 'site:nike.com "XX1234-001"'
            return httpx.Response(200, json={"organic_results": [{"title": "Nike", "link": page}]})
        if request.url.params["type"] == "exact_matches":
            return httpx.Response(200, json={"exact_matches": []})
        return httpx.Response(200, json={"visual_matches": [
            {"title": "Nike sweatshirt", "link": retailer if retailer_candidate else page, "image": reference},
        ]})

    mock_gemini(analyze)
    search = LensWebSearch("test-key", httpx.MockTransport(lens))
    app.dependency_overrides[get_lens_search] = lambda: search
    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    if image_retrieved:
        assert result["product_lookup"]["status"] == "matched"
        assert result["product_lookup"]["product"]["source_url"] == page
        assert result["product_care"]["max_wash_temperature_c"]["value"] == 30
        assert result["care_guidance_source"] == "official_product"
        assert result["photo_request"] is None
    else:
        assert result["product_lookup"]["status"] == "candidates"
        assert result["product_care"] == {}
        assert result["photo_request"]["image_type"] == "care_label"


@pytest.mark.parametrize("image_retrieved", [True, False])
@pytest.mark.parametrize("care_search_only", [False, True])
def test_lens_reads_care_from_an_uncatalogued_retailer_product(client, photo, image_retrieved, care_search_only):
    page = "https://www.29cm.co.kr/products/123456"
    lens_page = "https://example.com/item/87654306" if care_search_only else page
    reference = "https://img.29cm.co.kr/style-reference.jpg"

    def empty_catalog():
        return []

    app.dependency_overrides[catalog.get_catalog] = empty_catalog

    def analyze(request):
        payload = json.loads(request.content)
        if "tools" not in payload:
            return gemini_result({"image_type": "garment", "garment": {
                "brand": {"value": "푸마", "evidence": "Puma logo"},
            }})
        context = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert context["references"][0]["care_source"] == "product_listing"
        assert context["search_candidates"][0]["exact_match"] is True
        reading = gemini_result({
            "reference": 0, "match": "visual", "name": "푸마 컬러블록 상의",
            "brand": "PUMA", "color": "네이비", "product_code": "87654306",
            **({"candidate_index": 0, "retailer_product_code": "87654306"} if care_search_only else {}),
            "visual_evidence": ["소매의 삼각형 배색", "칼라에서 이어지는 흰색 파이핑"],
            "care": {"dry_in_shade": {"value": True, "evidence": "Dry in shade"}},
        }).json()
        retrieved = [page, lens_page]
        if image_retrieved:
            retrieved.append(reference)
        reading["candidates"][0]["urlContextMetadata"] = {"urlMetadata": [
            {"retrievedUrl": url, "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"}
            for url in retrieved
        ]}
        return httpx.Response(200, json=reading)

    def lens(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            query = request.url.params["q"]
            assert '"87654306"' in query
            matches = [{"title": "푸마 컬러블록 상의", "link": page}] if care_search_only and "세탁방법" in query else []
            return httpx.Response(200, json={"organic_results": matches})
        match = {"title": "푸마 컬러블록 상의 87654306", "link": lens_page, "thumbnail": reference}
        return httpx.Response(200, json={request.url.params["type"]: [match]})

    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(lens))
    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["photo_request"]["image_type"] == "care_label"
    if image_retrieved:
        assert result["product_lookup"]["product"]["source_url"] == page
        assert result["product_lookup"]["status"] == "matched"
        assert result["care_guidance_source"] == "product_listing"
        assert result["care_guidance"] == ["그늘에서 말리세요."]
        assert result["product_care"]["wash_method"]["value"] is None
    else:
        assert result["product_lookup"]["status"] == "candidates"
        assert result["product_care"] == {}


@pytest.mark.parametrize("page_retrieved", [True, False])
def test_lens_compares_the_search_photo_of_any_shop_page(client, photo, monkeypatch, page_retrieved):
    page = "https://shop.example.com/goods/774"
    thumbnail = "https://encrypted-tbn0.gstatic.com/images?q=tbn:test"
    def empty_catalog():
        return []

    app.dependency_overrides[catalog.get_catalog] = empty_catalog

    async def candidate_photos(candidates):
        assert str(candidates[0].thumbnail_url) == thumbnail
        return {catalog.official_url_key(candidates[0].source_url): photo}

    def analyze(request):
        payload = json.loads(request.content)
        if "tools" not in payload:
            return gemini_result({"image_type": "garment", "garment": {
                "garment_type": {"value": "후드 집업", "evidence": "지퍼와 후드"},
            }})
        parts = payload["contents"][0]["parts"]
        reference = json.loads(parts[0]["text"])["references"][0]
        assert reference["page_url"] == page and reference["has_inline_photo"]
        assert parts[-2]["text"] == "Product page reference photo 0"
        assert base64.b64decode(parts[-1]["inlineData"]["data"]) == photo
        reading = gemini_result({
            "reference": 0, "match": "visual", "brand": "Example", "name": "후드 집업 재킷", "color": "블루",
            "visual_evidence": ["같은 사진", "가슴의 지퍼 포켓"],
            "care": {"wash_method": {"value": "hand_wash", "evidence": "손세탁"}},
        }).json()
        reading["candidates"][0]["urlContextMetadata"] = {"urlMetadata": [
            {"retrievedUrl": page, "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"},
        ] if page_retrieved else []}
        return httpx.Response(200, json=reading)

    def lens(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            return httpx.Response(200, json={"organic_results": []})
        match = {"title": "후드 집업 재킷", "link": page, "image": "https://shop.example.com/774.jpg",
                 "thumbnail": thumbnail}
        return httpx.Response(200, json={request.url.params["type"]: [match]})

    monkeypatch.setattr(official_product, "read_candidate_photos", candidate_photos)
    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(lens))
    result = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}).json()

    if page_retrieved:
        assert result["product_lookup"]["status"] == "matched"
        assert result["product_lookup"]["product"]["source_url"] == page
        assert result["care_guidance_source"] == "product_listing"
        assert result["care_guidance"] == ["손세탁하세요."]
    else:
        # The matched search photo identifies the product, but care from an unread page is discarded.
        assert result["product_lookup"]["status"] == "matched"
        assert result["product_lookup"]["product"]["source_url"] == page
        assert result["care_guidance_source"] is None
        assert result["care_guidance"] == []
        assert "세탁 정보를 확실하게 알 수 없어요" in result["message"]
        assert result["product_care"]["wash_method"]["value"] is None
        assert result["photo_request"]["image_type"] == "care_label"


@pytest.mark.parametrize("care_profile", ["partial", "material_only", "none"])
def test_photo_analysis_precedes_search_and_product_verification(client, photo, monkeypatch, care_profile):
    page = "https://shop.example.com/goods/774"
    requests = []

    def empty_catalog():
        return []

    app.dependency_overrides[catalog.get_catalog] = empty_catalog

    async def candidate_photos(candidates):
        return {catalog.official_url_key(candidates[0].source_url): photo}

    garment = {"image_type": "garment", "garment": {
        "garment_type": {"value": "후드 집업", "evidence": "지퍼와 후드"},
        "brand": {"value": "Example", "evidence": "가슴 로고"},
    }}
    product = {
        "reference": 0, "match": "visual", "brand": "EXAMPLE", "name": "후드 집업 재킷", "color": "블루",
        "visual_evidence": ["같은 사진", "가슴의 지퍼 포켓"],
        "care": {
            "fiber_content": {
                "value": "면 84%, 폴리에스터 14%, 폴리우레탄 2%",
                "evidence": "면 84%, 폴리에스터 14%, 폴리우레탄 2%",
            },
            "wash_method": {"value": "machine_wash", "evidence": "세탁기 사용 가능"},
            "bleach": {"value": "표백 금지", "evidence": "Do not iron print"},
        },
        "material_tips": {"washing": "mesh_bag", "drying": "dry_in_shade"},
    }
    if care_profile != "partial":
        product["care"].pop("wash_method")
    if care_profile == "none":
        product["care"].pop("fiber_content")
        product.pop("material_tips")

    def analyze(request):
        payload = json.loads(request.content)
        if "tools" not in payload:
            requests.append("photo")
            return gemini_result(garment)
        requests.append("product")
        context = json.loads(payload["contents"][0]["parts"][0]["text"])
        # The search ran before the photo was read, so it had no clues from the photo.
        assert context["garment_clues"] is None
        reading = gemini_result(product).json()
        reading["candidates"][0]["urlContextMetadata"] = {"urlMetadata": [
            {"retrievedUrl": page, "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"},
        ]}
        return httpx.Response(200, json=reading)

    def lens(request):
        if request.method == "POST":
            requests.append("search")
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            return httpx.Response(200, json={"organic_results": []})
        match = {"title": "Example 후드 집업 재킷", "link": page, "thumbnail": "https://encrypted-tbn0.gstatic.com/images?q=t"}
        return httpx.Response(200, json={request.url.params["type"]: [match]})

    monkeypatch.setattr(official_product, "read_candidate_photos", candidate_photos)
    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(lens))
    result = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}).json()

    # One model request reads the photo and identifies the product after the image search.
    assert requests == ["search", "photo", "product"] and GEMINI_REQUESTS == ["combined"]
    assert result["garment"]["garment_type"]["value"] == "후드 집업"
    assert result["product_lookup"]["status"] == "matched"
    assert result["product_lookup"]["product"]["source_url"] == page
    if care_profile == "partial":
        assert result["care_guidance_source"] == "product_listing"
        assert result["care_guidance"][0] == "세탁기로 세탁할 수 있어요."
        estimated = result["care_guidance"][1:]
        assert all(line.startswith("소재 기준 권장: ") and " · " in line for line in estimated)
        assert any("물 온도 · " in line and "찬물 또는 30°C 이하" in line for line in estimated)
        assert any("세탁 방식 · " in line and "울·섬세 코스" in line for line in estimated)
        assert any("마찰 · " in line and "세탁망" in line for line in estimated)
        assert any("건조 · " in line and "평평하게 자연 건조" in line for line in estimated)
        # The mismatched extracted bleach value is discarded, so the topic remains an estimate.
        assert any("표백 · " in line and "피하는 편이 안전" in line for line in estimated)
        assert "판매처 상품 안내에서 확인한 항목" in result["message"]
        assert "잠정 권장 사항" in result["message"]
    elif care_profile == "material_only":
        assert result["care_guidance_source"] == "material_estimate"
        estimated = result["care_guidance"]
        assert estimated and all(line.startswith("소재 기준 권장: ") and " · " in line for line in estimated)
        assert any("물 온도 · " in line and "찬물 또는 30°C 이하" in line for line in estimated)
        assert any("세탁기 사용이 라벨에 허용되면" in line for line in estimated)
        assert any("탈수 · " in line and "짧고 낮은 강도" in line for line in estimated)
        assert any("표백 · " in line and "피하는 편이 안전" in line for line in estimated)
        assert any("다림질 · " in line and "110°C는 보수적 참고값" in line for line in estimated)
        assert any("건조 · " in line and "평평하게 자연 건조" in line for line in estimated)
        assert "잠정 관리 권장 사항" in result["message"]
    else:
        assert result["care_guidance_source"] is None
        assert result["care_guidance"] == []
        assert "세탁 정보를 확실하게 알 수 없어요" in result["message"]
    assert result["photo_request"]["image_type"] == "care_label"
    assert "capture_label" in result["next_actions"]
    assert result["product_care"]["dry_in_shade"]["status"] == "needs_confirmation"
    assert result["product_care"]["bleach"]["status"] == "needs_confirmation"


@pytest.mark.parametrize(("page_brand", "matched"), [("디스커버리 익스페디션", True), ("아디다스", False)])
def test_shop_brand_written_in_korean_matches_the_latin_logo(client, photo, monkeypatch, page_brand, matched):
    page = "https://www.musinsa.com/products/5560241"
    resale = [f"https://resale{index}.example.com/goods/1" for index in range(9)]
    def empty_catalog():
        return []

    app.dependency_overrides[catalog.get_catalog] = empty_catalog

    async def candidate_photos(candidates):
        # The shop page ranks below the first eight results and still needs its photo.
        assert str(candidates[-1].source_url) == page
        return {catalog.official_url_key(item.source_url): photo for item in candidates}

    def analyze(request):
        payload = json.loads(request.content)
        if "tools" not in payload:
            return gemini_result({"image_type": "garment", "garment": {
                "garment_type": {"value": "후드 재킷", "evidence": "후드와 지퍼"},
                "brand": {"value": "Discovery Expedition", "evidence": "밑단 로고"},
                "color": {"value": "블랙", "evidence": "검은색 겉감"},
            }})
        references = json.loads(payload["contents"][0]["parts"][0]["text"])["references"]
        # A known shop's product page precedes resale listings.
        assert references[0]["page_url"] == page and references[0]["has_inline_photo"]
        return gemini_result({
            "reference": 0, "match": "visual", "brand": page_brand, "name": "남성 후드 재킷",
            "visual_evidence": ["밑단의 같은 로고 위치", "같은 후드 스트링 구조"],
        })

    def lens(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            return httpx.Response(200, json={"organic_results": []})
        if request.url.params["type"] == "exact_matches":
            return httpx.Response(200, json={"exact_matches": []})
        return httpx.Response(200, json={"visual_matches": [
            *({"title": "중고 후드 재킷", "link": link, "thumbnail": "https://encrypted-tbn0.gstatic.com/images?q=r"}
              for link in resale),
            {"title": "남성 후드 재킷 - 사이즈 & 후기 | 무신사", "link": page,
             "image": "https://image.msscdn.net/images/goods_img/5560241_big.jpg"},
        ]})

    monkeypatch.setattr(official_product, "read_candidate_photos", candidate_photos)
    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(lens))
    result = client.post("/api/analyze", files={"image": ("garment.jpg", photo)}).json()

    if matched:
        assert result["product_lookup"]["status"] == "matched"
        assert result["product_lookup"]["product"]["source_url"] == page
        assert result["product_lookup"]["product"]["brand"] == page_brand
    else:
        assert result["product_lookup"]["status"] == "candidates"


def test_lens_uses_official_puma_variant_photo_and_published_care(client, photo, monkeypatch):
    canonical_url = HttpUrl("https://th.puma.com/th/en/pd/example/812345.html?dwvar_812345_color=01")

    async def read_puma_page(_, url):
        assert url.path == "/th/en/pd/812345.html" and url.query == "dwvar_812345_color=01"
        return ProductPage(canonical_url, "Style: 812345_01. Wash and iron inside out.", "81234501", photo)

    def analyze(request):
        payload = json.loads(request.content)
        if not payload["systemInstruction"]["parts"][0]["text"].startswith("Identify the exact product"):
            return gemini_result({"image_type": "garment", "garment": {
                "brand": {"value": "푸마", "evidence": "로고"},
            }})
        # The server supplied the text and photo of the only page, so the model opens no page.
        assert "tools" not in payload
        parts = payload["contents"][0]["parts"]
        reference = json.loads(parts[0]["text"])["references"][0]
        assert reference["page_url"] == str(canonical_url) and reference["has_inline_photo"]
        assert base64.b64decode(parts[-1]["inlineData"]["data"]) == photo
        return gemini_result({
            "reference": 0, "match": "visual", "name": "푸마 상의", "color": "블랙", "product_code": "812345-01",
            "visual_evidence": ["동일한 프린트 위치", "동일한 이중 봉제"],
            "care": {"wash_method": {"value": "machine_wash", "evidence": "Machine wash"}},
            "care_notes": [
                {"value": "뒤집어서 세탁하세요.", "evidence": "Wash and iron inside out"},
                {"value": "중성 세제를 쓰세요.", "evidence": "Use a mild detergent"},
            ],
        })

    def search(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            return httpx.Response(200, json={"organic_results": []})
        return httpx.Response(200, json={request.url.params["type"]: [
            {"title": "푸마 상의 812345-01", "link": "https://example.com/products/1"},
        ]})

    monkeypatch.setattr(official_product, "read_product_page", read_puma_page)
    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(search))
    response = client.post("/api/analyze", files={"image": ("garment.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["product_lookup"]["status"] == "matched"
    assert result["product_lookup"]["product"]["source_url"] == str(canonical_url)
    assert result["care_guidance_source"] == "official_product"
    assert result["care_guidance"] == ["뒤집어서 세탁하세요."]
    assert result["product_care"]["wash_method"]["value"] is None


@pytest.mark.parametrize("details", [["hem badge", "geometric print"], ["Nike logo"]])
def test_search_verifies_catalog_photo_before_showing_saved_official_care(client, photo, monkeypatch, details):
    reference = next(entry for entry in catalog.load_catalog() if entry.product.product_code == "HV4119-254")
    app.dependency_overrides[catalog.get_catalog] = lambda: [reference]

    async def read_image(_, entry):
        assert entry == reference
        return photo

    monkeypatch.setattr(catalog_photo, "read_reference_image", read_image)

    def analyze(request):
        payload = json.loads(request.content)
        if payload["systemInstruction"]["parts"][0]["text"].startswith("Identify the exact product"):
            parts = payload["contents"][0]["parts"]
            listed = json.loads(parts[0]["text"])["references"][0]
            # The registered photo of the catalog product is supplied next to the upload.
            assert listed["catalog_id"] == reference.product.id and listed["has_inline_photo"]
            assert len([part for part in parts if "inlineData" in part]) == 2
            return gemini_result({
                "reference": 0, "match": "visual", "name": reference.product.name, "visual_evidence": details,
            })
        return gemini_result({"image_type": "garment", "garment": {
            "brand": {"value": "Nike", "evidence": "스우시"},
        }})

    def search(request):
        if request.method == "POST":
            return httpx.Response(200, json={"image_id": "test-id"})
        if request.url.params["engine"] == "google":
            return httpx.Response(200, json={"organic_results": []})
        return httpx.Response(200, json={request.url.params["type"]: [
            {"title": "Nike crew HV4119-254", "link": "https://example.com/products/123"},
        ]})

    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(search))
    response = client.post("/api/analyze", files={"image": ("photo.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["photo_request"]["image_type"] == "care_label"
    if len(details) == 2:
        assert result["product_lookup"]["product"]["product_code"] == "HV4119-254"
        assert result["care_guidance_source"] == "official_product"
        assert result["product_care"]["wash_method"]["value"] == "machine_wash"
        assert result["product_care"]["max_wash_temperature_c"]["value"] is None
    else:
        assert result["product_lookup"]["status"] == "candidates"
        assert result["product_care"] == {}


def test_official_lookup_quota_is_explained_in_the_photo_response(client, photo):
    def analyze(request):
        if "tools" in json.loads(request.content):
            return httpx.Response(429)
        return gemini_result({"image_type": "garment", "garment": {
            "brand": {"value": "Nike", "evidence": "NIKE"},
            "product_code": {"value": "TEST-001", "evidence": "STYLE TEST-001"},
        }})

    mock_gemini(analyze)
    app.dependency_overrides[get_lens_search] = lambda: LensWebSearch("test-key", httpx.MockTransport(
        lambda request: httpx.Response(200, json={"image_id": "test-id"} if request.method == "POST" else {
            key: [{"title": "Nike", "link": "https://www.nike.com/t/example/TEST-001"}]
            for key in ("organic_results", "visual_matches", "exact_matches")
        }),
    ))
    response = client.post("/api/analyze", files={"image": ("tag.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert "사용량 제한" in result["search_warning"]
    assert result["search_warning"] in result["message"]
    assert result["product_care"] == {}
