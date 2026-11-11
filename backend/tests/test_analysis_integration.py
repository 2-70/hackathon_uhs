import json
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.ai.gemini import GeminiAnalyzer
from backend.app.ai.router import get_analyzer
from backend.app.api import router
from backend.app.db.session import get_db
from backend.seed.load_verified import load_seed_data
from backend.seed.washwise_demo import verified_seed
from backend.tests.test_catalog_api import seed_catalog


@pytest.mark.parametrize(("printed", "status", "found"), [
    (["drum 20"], "matched", ["DRUM-20"]),
    (["WA10TESTW", "0412345678"], "candidates", ["WA10 TEST"]),
    (["ZZ99NONE"], "not_found", []),
    ([], "not_found", []),
])
def test_machine_photo_finds_the_printed_model(db_session, monkeypatch, printed, status, found):
    monkeypatch.setattr(router, "get_settings", lambda: SimpleNamespace(enable_ai_router=True))
    app = FastAPI()
    app.include_router(router.api_router)
    router.include_optional_ai_router(app)
    app.dependency_overrides[get_db] = lambda: db_session
    seed_catalog(db_session)

    def gemini(request):
        payload = json.loads(request.content)
        assert "washing machine" in payload["systemInstruction"]["parts"][0]["text"]
        reading = {"manufacturer": "테스트전자", "model_codes": printed}
        return httpx.Response(200, json={"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(reading)}]},
        }]})

    analyzer = GeminiAnalyzer(api_key="test-key", transport=httpx.MockTransport(gemini))
    app.dependency_overrides[get_analyzer] = lambda: analyzer
    photo = BytesIO()
    Image.new("RGB", (12, 12), "white").save(photo, format="JPEG")
    with TestClient(app) as client:
        response = client.post("/api/machines/identify", files={"image": ("washer.jpg", photo.getvalue())})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == status
    assert [item["model_name"] for item in result["catalog_models"]] == found
    # 일련번호처럼 글자와 숫자가 섞이지 않은 표기는 모델명으로 쓰지 않습니다.
    assert "0412345678" not in result["model_codes"]


def test_shared_app_matches_verified_database_rows(db_session, monkeypatch):
    monkeypatch.setattr(router, "get_settings", lambda: SimpleNamespace(enable_ai_router=True))
    app = FastAPI()
    app.include_router(router.api_router)
    router.include_optional_ai_router(app)
    app.dependency_overrides[get_db] = lambda: db_session

    seed = verified_seed()
    load_seed_data(db_session, seed)
    # Use a distinct DB value so the test detects an accidental JSON-file fallback.
    seed["products"][1]["product_name"] = "DB 테스트 상품"
    load_seed_data(db_session, seed)
    with TestClient(app) as client:
        match = client.post("/api/products/match", json={"brand": "Nike", "product_code": "IX1937-001"})
        assert match.status_code == 200
        assert match.json()["product"]["name"] == "DB 테스트 상품"
        care = client.get("/api/products/nike-ix1937-001/care").json()
        assert care["product_care"]["wash_method"]["evidence"] == "세탁기 사용 가능"
        assert care["product_care"]["max_wash_temperature_c"]["value"] is None

        machines = client.get("/api/machines", params={"query": "WM4000HWA"}).json()
        courses = client.get(f'/api/machines/{machines[0]["id"]}/courses').json()["courses"]
        assert len(machines) == 1 and len(courses) == 3
        normal = next(item for item in courses if item["course_key"] == "normal")["settings"]
        assert len(normal) == 1 and normal[0]["temperature_setting"] == "Warm"
        assert normal[0]["temperature_celsius"] is None and normal[0]["spin_rpm"] is None
