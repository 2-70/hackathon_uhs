import pytest
from fastapi.testclient import TestClient

from backend.app.ai import catalog
from backend.app.ai.preview import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_VISION_API_KEY", raising=False)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_match_brand_and_full_code_then_fetch_care(client):
    match = client.post("/api/products/match", json={"brand": "나이키", "product_code": "ix1937-001"})
    assert match.status_code == 200
    result = match.json()
    assert result["match_method"] == "product_code"
    assert result["product"]["id"] == "nike-ix1937-001"

    care = client.get(f'/api/products/{result["product"]["id"]}/care')
    assert care.status_code == 200
    data = care.json()
    assert data["product"]["source_url"] == result["product"]["source_url"]
    assert data["product_care"]["wash_method"]["status"] == "verified"
    assert data["product_care"]["fiber_content"]["value"] == "면 82%, 폴리에스터 18%"
    assert data["product_care"]["max_wash_temperature_c"]["status"] == "needs_confirmation"
    assert data["product_care"]["tumble_dry_allowed"]["value"] is None
    assert data["photo_request"]["image_type"] == "care_label"


def test_official_url_allows_tracking_but_not_unknown_variant(client):
    source_url = str(catalog.load_catalog()[1].product.source_url)
    match = client.post("/api/products/match", json={"source_url": f"{source_url}?utm_source=demo"})
    assert match.status_code == 200
    assert match.json()["match_method"] == "official_url"

    variant = client.post("/api/products/match", json={"source_url": f"{source_url}?color=other"})
    assert variant.status_code == 200
    assert variant.json()["status"] == "not_found"


def test_conflicting_identifiers_return_candidates_without_claiming_a_match(client):
    source_url = str(catalog.load_catalog()[1].product.source_url)
    response = client.post("/api/products/match", json={
        "brand": "Nike", "product_code": "IF0698-365", "source_url": source_url,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "candidates"
    assert response.json()["product"] is None
    assert len(response.json()["candidates"]) == 2


def test_appearance_is_only_a_candidate_and_unrelated_clues_are_not_found(client):
    response = client.post("/api/products/match", json={"brand": "나이키", "garment_type": "맨투맨"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "candidates"
    assert result["product"] is None
    assert len(result["candidates"]) == 2

    unmatched = client.post("/api/products/match", json={"brand": "다른 브랜드", "garment_type": "맨투맨"})
    assert unmatched.json()["status"] == "not_found"
    assert client.get("/api/products/unknown/care").status_code == 404


def test_unavailable_catalog_is_distinct_from_no_match(client, monkeypatch):
    def unavailable():
        raise OSError("catalog unavailable")

    monkeypatch.setattr(catalog, "load_catalog", unavailable)
    match = client.post("/api/products/match", json={"brand": "Nike", "garment_type": "맨투맨"})
    assert match.status_code == 503
    assert match.json()["status"] == "search_unavailable"
    assert client.get("/api/products/nike-ix1937-001/care").status_code == 503
