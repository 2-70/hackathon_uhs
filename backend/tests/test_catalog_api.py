"""카탈로그 페이지네이션·통계·공식 사용법 API를 검증합니다."""

from datetime import date

from backend.app.db.models import (
    CatalogDocument,
    CatalogModel,
    CatalogModelDocument,
    CatalogSource,
    CatalogSourceRecord,
    CatalogUsageInstruction,
    new_id,
    utc_now,
)


def seed_catalog(db_session) -> tuple[CatalogModel, CatalogModel]:
    """검색과 사용법 조회에 필요한 최소 카탈로그를 만듭니다."""

    first = CatalogModel(
        id=new_id(),
        catalog_key="test-general-1",
        machine_family="general_washer",
        use_type="household",
        market_region="KR",
        model_name="WA10 TEST",
        normalized_model_name="WA10TEST",
        applicant_name="테스트전자(주)",
        manufacturer_name="테스트전자",
        origin_claim="국산",
        capacity_kg=10,
        latest_registration_completed_on=date(2025, 1, 1),
        market_status="candidate",
        evidence_status="market_evidence_only",
        recommendation_status="catalog_only",
        source_url="https://example.invalid/list",
    )
    second = CatalogModel(
        id=new_id(),
        catalog_key="test-drum-1",
        machine_family="drum_washer",
        use_type="household",
        market_region="KR",
        model_name="DRUM-20",
        normalized_model_name="DRUM-20",
        applicant_name="다른전자",
        manufacturer_name=None,
        origin_claim="수입",
        capacity_kg=20,
        latest_registration_completed_on=date(2024, 1, 1),
        market_status="candidate",
        evidence_status="market_evidence_only",
        recommendation_status="catalog_only",
        source_url="https://example.invalid/list",
    )
    source = CatalogSource(
        id=new_id(),
        source_key="test-source",
        name="테스트 자료원",
        authority="테스트 기관",
        country_code="KR",
        category="test",
        source_url="https://example.invalid/list",
        reported_count=1,
        last_checked_at=utc_now(),
    )
    document = CatalogDocument(
        id=new_id(),
        document_key="doc-key",
        source_url="https://example.invalid/manual.pdf",
        title="WA10 TEST 사용설명서",
        language="ko",
        media_type="application/pdf",
        content_sha256="a" * 64,
        page_count=20,
        retrieval_status="retrieved",
        extraction_status="structured",
        model_scope_text="WA10 TEST",
        retrieved_at=utc_now(),
    )
    db_session.add_all([first, second, source, document])
    db_session.flush()
    db_session.add(
        CatalogSourceRecord(
            id=new_id(),
            source_id=source.id,
            catalog_model_id=first.id,
            source_record_key="record-key",
            source_row_number=1,
            completed_on=date(2025, 1, 1),
            model_name_raw=first.model_name,
            applicant_name_raw=first.applicant_name,
            manufacturer_name_raw=first.manufacturer_name,
            origin_claim_raw=first.origin_claim,
            capacity_kg=first.capacity_kg,
            efficiency_grade_raw="1",
            eligibility_status="candidate",
            eligibility_reason="official_kr_registration_in_period",
            raw_data={"모델명": first.model_name},
            content_sha256="b" * 64,
            first_seen_at=utc_now(),
            last_seen_at=utc_now(),
        )
    )
    db_session.add(
        CatalogModelDocument(
            id=new_id(),
            catalog_model_id=first.id,
            document_id=document.id,
            matching_method="official_exact_model",
            matching_status="confirmed",
            exact_model_match=True,
            evidence="공식 설명서 제목의 정확 모델명",
        )
    )
    db_session.add(
        CatalogUsageInstruction(
            id=new_id(),
            catalog_model_id=first.id,
            document_id=document.id,
            instruction_key="usage-key",
            category="start_sequence",
            title="세탁 시작",
            instruction_text="전원을 켜고 코스를 선택한 뒤 시작 버튼을 누릅니다.",
            page_number=5,
            evidence_excerpt="전원 → 코스 → 시작",
            review_status="confirmed",
        )
    )
    db_session.commit()
    return first, second


def test_catalog_search_stats_and_usage(client, db_session):
    """페이지 검색과 저장 건수, 정확 모델 사용법을 실제 HTTP 경로로 확인합니다."""

    first, _ = seed_catalog(db_session)
    page_response = client.get("/api/catalog/models", params={"page_size": 1, "query": "wa10"})
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["total"] == 1
    assert page["total_pages"] == 1
    assert page["items"][0]["model_name"] == "WA10 TEST"

    stats_response = client.get("/api/catalog/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["model_total"] == 2
    assert stats["source_record_total"] == 1
    assert stats["models_with_document"] == 1
    assert stats["structured_instruction_total"] == 1

    usage_response = client.get(f"/api/catalog/models/{first.id}/usage")
    assert usage_response.status_code == 200
    usage = usage_response.json()
    assert usage["documents"][0]["exact_model_match"] is True
    assert usage["instructions"][0]["category"] == "start_sequence"
    assert usage["instructions"][0]["review_status"] == "confirmed"

