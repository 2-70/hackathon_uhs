import pytest
from fastapi.testclient import TestClient

from backend.app.ai import catalog
from backend.app.ai.preview import app
from backend.app.ai.schemas import LabelReadings, MaterialCareTips


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


def test_material_tips_are_estimated_and_do_not_override_care():
    entry = catalog.load_catalog()[1]
    fibers = {"fiber_content": {"value": "울 40%, 면 60%", "evidence": "울 40%, 면 60%"}}
    tips = MaterialCareTips(washing="wool_detergent", drying="dry_flat")
    material_only = catalog.describe_product_care(entry.model_copy(update={
        "care": LabelReadings.model_validate(fibers), "material_tips": tips,
    }))
    assert material_only.care_guidance_source == "material_estimate"
    assert any("울" in line and "찬물" in line for line in material_only.care_guidance)
    assert any(
        "세탁기 사용이" in line and "손세탁이 허용되면" in line
        for line in material_only.care_guidance
    )
    assert material_only.product_care["wash_method"].value is None
    assert material_only.product_care["natural_dry"].value is None

    padded = catalog.describe_product_care(entry.model_copy(update={
        "care": LabelReadings.model_validate(fibers), "material_tips": tips,
    }), observed_type="패딩")
    assert padded.product.source_url == entry.product.source_url
    assert padded.care_guidance == []
    assert "충전재" in padded.photo_request.instructions

    published = catalog.describe_product_care(entry.model_copy(update={
        "care": LabelReadings.model_validate({**fibers,
            "wash_method": {"value": "do_not_wash", "evidence": "물세탁 금지"},
            "natural_dry": {"value": "line_dry", "evidence": "걸어서 말리세요."},
        }),
        "material_tips": tips,
    }))
    assert published.care_guidance_source == "official_product"
    assert published.care_guidance == ["물세탁을 피하세요.", "옷을 걸어서 말리세요."]


def test_verified_shop_materials_get_conditional_material_guidance(client):
    match = client.post("/api/products/match", json={"brand": "Nike", "product_code": "HV4119-254"})
    assert match.status_code == 200
    product_id = match.json()["product"]["id"]
    assert product_id == "nike-hv4119-254"

    actual = client.get(f"/api/products/{product_id}/care").json()
    assert actual["product_care"]["wash_method"]["value"] == "machine_wash"
    assert actual["product_care"]["max_wash_temperature_c"]["value"] is None
    assert actual["product_care"]["max_wash_temperature_c"]["status"] == "needs_confirmation"
    actual_guidance = actual["care_guidance"]
    assert any("물 온도" in line and "30" in line for line in actual_guidance)
    assert any("세탁 방식" in line and "라벨의 허용 범위" in line and "코스" in line
               for line in actual_guidance)
    assert any("세제" in line and "중성세제" in line for line in actual_guidance)
    assert any("마찰" in line and "세탁망" in line for line in actual_guidance)
    assert any("탈수" in line and "짧고 낮은 강도" in line for line in actual_guidance)
    assert any("건조" in line and "그늘" in line for line in actual_guidance)
    assert any("다림질" in line and "허용된 경우" in line and "저온" in line for line in actual_guidance)
    assert actual["photo_request"]["image_type"] == "care_label"
    assert "capture_label" in actual["next_actions"]
    assert "옷 안쪽 세탁 라벨" in actual["message"]
    assert "찍어 주세요" in actual["message"]

    entry = next(item for item in catalog.load_catalog() if item.product.product_code == "HV4119-254")
    shop_materials = "84% 면, 16% 폴리에스터 / 골지: 98% 면, 2% 폴리우레탄"
    fiber = entry.care.fiber_content.model_copy(update={"value": shop_materials, "evidence": shop_materials})
    care = entry.care.model_copy(update={"fiber_content": fiber})
    response = catalog.describe_product_care(entry.model_copy(update={"care": care}))
    guidance = response.care_guidance

    assert any(line.startswith("소재 기준 권장: 물 온도") and "30" in line for line in guidance)
    assert any("라벨의 허용 범위에서" in line and "코스" in line for line in guidance)
    assert any(line.startswith("소재 기준 권장: 세제") and "중성세제" in line for line in guidance)
    assert any("마찰" in line and "세탁망" in line for line in guidance)
    assert any(line.startswith("소재 기준 권장: 탈수") and "짧고 낮은 강도" in line for line in guidance)
    assert any(line.startswith("소재 기준 권장: 건조") and "그늘" in line for line in guidance)
    assert any(
        line.startswith("소재 기준 권장: 다림질") and "허용된 경우" in line and "저온" in line
        for line in guidance
    )

    known_care = LabelReadings.model_validate({
        **care.model_dump(exclude_none=True),
        "max_wash_temperature_c": {"value": 30, "evidence": "세탁통 안 숫자 30"},
        "wash_cycle": {"value": "gentle", "evidence": "약한 코스"},
    })
    with_confirmed_settings = catalog.describe_product_care(entry.model_copy(update={"care": known_care}))
    material_guidance = [
        line for line in with_confirmed_settings.care_guidance if line.startswith("소재 기준 권장: ")
    ]
    assert not any(line.startswith("소재 기준 권장: 물 온도") for line in material_guidance)
    assert not any("라벨의 허용 범위에서" in line and "코스" in line for line in material_guidance)


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
    assert len(result["candidates"]) == 3

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
