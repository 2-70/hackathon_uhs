import asyncio
import json
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.ai import gemini
from backend.app.ai.gemini import GeminiAnalyzer, GeminiError
from backend.app.ai.preview import app
from backend.app.ai.router import get_analyzer, prepare_image


def success():
    return httpx.Response(200, json={"candidates": [{
        "finishReason": "STOP", "content": {"parts": [{"text": '{"image_type":"unknown"}'}]},
    }]})


def test_gemini_uses_first_working_backup_after_credential_and_quota_errors():
    attempted = []

    def handler(request):
        key = request.headers["x-goog-api-key"]
        attempted.append(key)
        if key == "invalid":
            return httpx.Response(403)
        if key == "exhausted":
            return httpx.Response(429)
        return success()

    analyzer = GeminiAnalyzer(
        "invalid", backup_keys=("exhausted", "working"), transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto"))

    assert result.image_type == "unknown"
    assert attempted == ["invalid", "exhausted", "working"]
    assert analyzer.api_key == "working"


def test_daily_quota_pauses_a_model_until_the_reset_and_a_minute_limit_for_a_minute():
    per_minute = httpx.Response(429, json={"error": {"details": [{"violations": [
        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"},
    ]}]}})
    per_day = httpx.Response(429, json={"error": {"details": [{"violations": [
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"},
    ]}]}})

    assert gemini.quota_pause_seconds(per_minute) == 60
    # A daily limit, or a reply that names no limit, keeps the model paused until midnight Pacific time.
    for reply in (per_day, httpx.Response(429)):
        assert 0 < gemini.quota_pause_seconds(reply) <= 24 * 3600


def test_spent_quota_is_checked_once_before_switching_models():
    attempted = []

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        attempted.append((model, request.headers["x-goog-api-key"]))
        return httpx.Response(429) if model == gemini.DEFAULT_MODEL else success()

    analyzer = GeminiAnalyzer("first", backup_keys=("second", "third"), transport=httpx.MockTransport(handler))
    for _ in range(2):
        assert asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto")).image_type == "unknown"

    # The first request learns that every key is out of quota. The next one goes straight to the other model.
    assert attempted == [
        (gemini.DEFAULT_MODEL, "first"), (gemini.DEFAULT_MODEL, "second"), (gemini.DEFAULT_MODEL, "third"),
        (gemini.QUOTA_FALLBACK_MODEL, "first"), (gemini.QUOTA_FALLBACK_MODEL, "first"),
    ]


@pytest.mark.parametrize("failure", [429, 500, 503, "timeout", "connection"])
def test_transient_failure_recovers_without_user_resubmitting(monkeypatch, failure):
    calls = []
    monkeypatch.setattr(gemini, "retry_delay", lambda *_: 0)

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("private network details", request=request)
            if failure == "connection":
                raise httpx.ConnectError("private network details", request=request)
            return httpx.Response(failure)
        return success()

    analyzer = GeminiAnalyzer("test-key", transport=httpx.MockTransport(handler))
    result = asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto"))
    assert result.image_type == "unknown"
    assert len(calls) == 2
    if failure == 429:
        # A request limit is counted per model, so the same photo goes to the quota fallback model.
        assert calls[1].url.path.endswith(f"models/{gemini.QUOTA_FALLBACK_MODEL}:generateContent")
        assert json.loads(calls[0].content)["contents"] == json.loads(calls[1].content)["contents"]
    else:
        assert calls[0].content == calls[1].content


@pytest.mark.parametrize("status,reason,code", [
    (400, "API_KEY_INVALID", "analysis_key_invalid"),
    (403, "API_KEY_SERVICE_BLOCKED", "analysis_key_restricted"),
    (404, "", "analysis_model_unavailable"),
])
def test_permanent_configuration_error_is_not_retried(status, reason, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"details": [{"reason": reason}]}})

    analyzer = GeminiAnalyzer("test-key", transport=httpx.MockTransport(handler))
    with pytest.raises(GeminiError) as caught:
        asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto"))
    assert caught.value.code == code
    assert len(calls) == 1


def test_persistent_outage_has_bounded_attempts(monkeypatch):
    calls = []
    monkeypatch.setattr(gemini, "retry_delay", lambda *_: 0)

    def handler(request):
        calls.append(request)
        return httpx.Response(503, text="private upstream details")

    analyzer = GeminiAnalyzer("test-key", transport=httpx.MockTransport(handler))
    with pytest.raises(GeminiError) as caught:
        asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto"))
    assert caught.value.code == "analysis_provider_unavailable"
    assert len(calls) == 3
    assert "private" not in str(caught.value)


def test_unavailable_primary_switches_to_flash_fallback():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else success()

    analyzer = GeminiAnalyzer("test-key", fallback_model=gemini.FALLBACK_MODEL, transport=httpx.MockTransport(handler))
    result = asyncio.run(analyzer.analyze(b"label-photo", "image/png", "care_label"))

    assert result.image_type == "unknown"
    assert [request.url.path.split("/")[-1] for request in calls] == [
        "gemini-3.6-flash:generateContent",
        "gemini-3.5-flash:generateContent",
    ]
    assert json.loads(calls[0].content) == json.loads(calls[1].content)
    assert calls[0].headers["x-goog-api-key"] == calls[1].headers["x-goog-api-key"]


def test_retry_after_cannot_exceed_total_deadline(monkeypatch):
    monkeypatch.setattr(gemini, "TOTAL_TIMEOUT_SECONDS", 0.02)
    analyzer = GeminiAnalyzer("test-key", transport=httpx.MockTransport(
        lambda _: httpx.Response(429, headers={"Retry-After": "3600"})))
    with pytest.raises(GeminiError) as caught:
        asyncio.run(analyzer.analyze(b"photo", "image/jpeg", "auto"))
    assert caught.value.code == "analysis_timeout"


def test_retry_after_is_respected():
    assert gemini.retry_delay(httpx.Response(429, headers={"Retry-After": "12"}), 0) == 12


@pytest.mark.parametrize(("image_type", "expected_size"), [
    ("auto", (1280, 2560)),
    ("care_label", (1536, 3072)),
])
def test_high_resolution_small_file_is_resized_and_rotated(image_type, expected_size):
    buffer = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (4000, 2000), "white").save(buffer, format="JPEG", exif=exif)
    image, mime_type = prepare_image(buffer.getvalue(), image_type)
    with Image.open(BytesIO(image)) as decoded:
        assert decoded.size == expected_size
        assert decoded.getexif().get(274) is None
    assert mime_type == "image/jpeg"


def test_reference_photo_remains_available_without_a_gemini_key(monkeypatch):
    from hashlib import sha256

    from backend.app.ai import catalog

    buffer = BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format="JPEG")
    photo = buffer.getvalue()
    entry = catalog.load_catalog()[0].model_copy(update={"image_sha256": [sha256(photo).hexdigest()]})
    monkeypatch.setattr(catalog, "load_catalog", lambda: [entry])

    def handler(_):
        pytest.fail("An unconfigured analyzer must not send a request")

    app.dependency_overrides[get_analyzer] = lambda: GeminiAnalyzer(None, transport=httpx.MockTransport(handler))
    try:
        with TestClient(app) as client:
            response = client.post("/api/analyze", files={"image": ("photo.jpg", photo)})
        assert response.status_code == 200
        assert response.json()["care_guidance_source"] == "official_product"
    finally:
        app.dependency_overrides.clear()


def test_preview_checks_real_generation_and_hides_key():
    from backend.app.ai.connection import check_connection

    def handler(request):
        assert request.url.path.endswith(":generateContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        return success()

    asyncio.run(check_connection(" test-key ", "gemini-3.1-flash-lite", httpx.MockTransport(handler)))


def test_probe_does_not_report_ready_for_truncated_generation():
    from backend.app.ai.connection import check_connection

    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"candidates": [{
        "finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "incomplete"}]},
    }]}))
    with pytest.raises(GeminiError) as caught:
        asyncio.run(check_connection("test-key", "gemini-3.1-flash-lite", transport))
    assert caught.value.code == "analysis_probe_failed"


def test_launcher_reprompts_invalid_key_without_restart(monkeypatch):
    from backend.tests.ai import launch_preview

    monkeypatch.setenv("GEMINI_API_KEY", "bad-test-key")
    monkeypatch.setattr(launch_preview.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(launch_preview, "getpass", lambda _: "good-test-key")
    keys = []

    async def check(key, model):
        keys.append(key)
        if key == "bad-test-key":
            raise GeminiError(503, "analysis_key_invalid", "Invalid key")

    monkeypatch.setattr(launch_preview, "check_connection", check)
    assert launch_preview.ensure_connection()
    assert keys == ["bad-test-key", "good-test-key"]


def test_launcher_does_not_start_after_failed_noninteractive_probe(monkeypatch):
    from backend.tests.ai import launch_preview

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(launch_preview.sys.stdin, "isatty", lambda: False)

    async def check(*_):
        raise GeminiError(504, "analysis_connection_timeout", "Timed out")

    monkeypatch.setattr(launch_preview, "check_connection", check)
    monkeypatch.setattr(launch_preview, "start_server", lambda _: pytest.fail("Must not start server"))
    assert launch_preview.main() == 1
