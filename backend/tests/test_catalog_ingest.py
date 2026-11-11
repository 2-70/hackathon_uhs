"""한국에너지공단 목록 파싱·기간 판정·반복 적재를 검증합니다."""

from sqlalchemy import func, select

from backend.app.catalog_ingest.kea import (
    KeaSourceSpec,
    classify_record,
    ingest_records,
    make_catalog_key,
    normalize_model_name,
    parse_kea_export,
    summarize_records,
)
from backend.app.db.models import (
    CatalogIngestionRun,
    CatalogModel,
    CatalogSource,
    CatalogSourceRecord,
)


def sample_export() -> bytes:
    """현행 파일과 같은 CP949 HTML 표를 작은 테스트 데이터로 만듭니다."""

    html = """
    <html><body><table>
      <tr><td colspan="11">제품 상세 항목</td></tr>
      <tr>
        <th>번호</th><th>업체명</th><th>완료일자</th><th>모델명</th>
        <th>시험기관</th><th>제조원</th><th>국산/수입</th>
        <th>표준세탁용량(kg)</th><th>소비전력량</th><th>효율등급</th><th>지표</th>
      </tr>
      <tr>
        <td>1</td><td>테스트전자(주)</td><td>2026-01-02</td><td>WW-10 A</td>
        <td>공식시험원</td><td>테스트전자</td><td>국산</td>
        <td>10</td><td>100</td><td>1</td><td>10</td>
      </tr>
      <tr>
        <td>2</td><td>과거전자</td><td>2010-01-02</td><td>OLD-1</td>
        <td>공식시험원</td><td>과거전자</td><td>국산</td>
        <td>8</td><td>120</td><td>2</td><td>12</td>
      </tr>
    </table></body></html>
    """
    return html.encode("cp949")


def test_parse_and_classify_kea_export():
    """원문 모델명은 보존하고 기간 밖 행은 명시적으로 제외해야 합니다."""

    records = parse_kea_export(sample_export())
    assert len(records) == 2
    assert records[0].model_name == "WW-10 A"
    assert records[0].capacity_kg == 10.0
    assert classify_record(records[0]) == ("candidate", "official_kr_registration_in_period")
    assert classify_record(records[1]) == (
        "excluded",
        "registration_completed_before_period",
    )
    # 검색 키의 공백은 제거하지만 하이픈과 접미사는 그대로 구분합니다.
    assert normalize_model_name("ww-10 a") == "WW-10A"
    assert make_catalog_key("general_washer", "WW-10 A") == make_catalog_key(
        "general_washer", "ww-10a"
    )


def test_ingest_is_idempotent_and_preserves_excluded_records(db_session):
    """같은 공식 파일을 두 번 적재해도 모델과 원본 행이 늘지 않아야 합니다."""

    spec = KeaSourceSpec(
        source_key="test-kea-general",
        name="테스트 일반 세탁기",
        category="test_general",
        machine_family="general_washer",
        export_url="https://example.invalid/export",
        list_url="https://example.invalid/list",
        reported_count=2,
    )
    raw = sample_export()
    records, first_summary = summarize_records(spec, raw, 0.1)
    ingest_records(db_session, spec, records, first_summary)
    # 두 번째 실행도 같은 안정 키로 upsert되어 데이터 행 수가 유지됩니다.
    records, second_summary = summarize_records(spec, raw, 0.1)
    ingest_records(db_session, spec, records, second_summary)

    assert db_session.scalar(select(func.count()).select_from(CatalogSource)) == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogModel)) == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogSourceRecord)) == 2
    assert db_session.scalar(select(func.count()).select_from(CatalogIngestionRun)) == 2
    stored_model = db_session.scalar(select(CatalogModel))
    assert stored_model is not None
    assert stored_model.market_status == "candidate"
    assert stored_model.recommendation_status == "catalog_only"
    excluded = db_session.scalar(
        select(CatalogSourceRecord).where(CatalogSourceRecord.eligibility_status == "excluded")
    )
    assert excluded is not None
    assert excluded.catalog_model_id is None

