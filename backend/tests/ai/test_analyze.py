import base64
import json
from hashlib import sha256
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from backend.app.ai import catalog
from backend.app.ai import router as image_router
from backend.app.ai.gemini import GeminiAnalyzer
from backend.app.ai.preview import app
from backend.app.ai.router import get_analyzer, get_web_search
from backend.app.ai.web_search import VisionWebSearch


@pytest.fixture
def photo():
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_VISION_API_KEY", raising=False)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def mock_gemini(handler):
    analyzer = GeminiAnalyzer(api_key="test-key", transport=httpx.MockTransport(handler))
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


def test_unmatched_garment_photo_requests_label_and_discards_guessed_settings(client, photo):
    suggestion = {
        "sorting": "separate_dark_colors",
        "washing": "30°C로 세탁하세요.",
        "drying": "건조기를 쓰세요.",
    }

    def handler(request):
        payload = json.loads(request.content)
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert "photo_issue" in schema["properties"]
        assert set(schema["$defs"]["PhotoCareSuggestion"]["properties"]) == {"sorting"}
        return gemini_result({"image_type": "garment", "garment": {
            "garment_type": {"value": "스웨트셔츠", "evidence": "긴 소매와 둥근 목"},
            "color": {"value": "다크 그레이", "evidence": "짙은 회색"},
            "product_code": {"value": "ABC-123", "evidence": "옷에 ABC-123이라고 인쇄됨"},
        }, "photo_care": suggestion})

    mock_gemini(handler)
    response = client.post("/api/analyze", files={"image": ("shirt.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["image_type"] == "garment"
    assert result["status"] == "needs_confirmation"
    assert result["garment"]["product_code"]["value"] == "ABC-123"
    assert result["garment"]["product_code"]["status"] == "estimated"
    assert result["garment"]["brand"]["status"] == "needs_confirmation"
    assert result["care_guidance_source"] == "estimated"
    assert result["care_guidance"] == ["물세탁이 가능한 옷이라면 밝은 옷과 분리해 세탁하세요."]
    assert result["product_care"] == {}
    assert result["next_actions"] == ["capture_label", "manual_entry"]
    assert result["photo_request"]["image_type"] == "care_label"
    assert "옆 솔기" in result["photo_request"]["instructions"]
    assert "네모 모양의 건조 기호" in result["message"]


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

    label = client.post(
        "/api/analyze", files={"image": ("label.jpg", photo)},
        data={"image_type": data["photo_request"]["image_type"]},
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
    assert result["care_guidance"] == []
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


def test_unrelated_photo_requests_another_photo(client, photo):
    mock_gemini(lambda _: gemini_result({"image_type": "unknown"}))
    response = client.post("/api/analyze", files={"image": ("other.jpg", photo)})
    assert response.status_code == 200
    result = response.json()
    assert result["next_actions"] == ["retake_photo", "manual_entry"]
    assert result["photo_request"]["image_type"] == "garment"
    assert "앞면 전체" in result["photo_request"]["instructions"]


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
    assert result["care_guidance"] == ["손세탁하세요.", "드라이클리닝도 가능해요.", "뒤집어서 세탁하는 방법은 권장하지 않아요."]
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
        assert result["care_guidance"] == []
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
