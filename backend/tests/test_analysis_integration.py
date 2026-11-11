from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import router
from backend.app.db.session import get_db
from backend.seed.load_verified import load_seed_data
from backend.seed.washwise_demo import verified_seed


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
