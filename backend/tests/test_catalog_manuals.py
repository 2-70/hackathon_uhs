"""공식 설명서 업체 선택과 삼성 AJAX 파싱을 검증합니다."""

from backend.app.catalog_ingest.manuals import parse_samsung_manual_html, select_adapter
from backend.app.db.models import CatalogModel, new_id


def catalog_model(applicant: str | None) -> CatalogModel:
    """업체별 공식 어댑터 선택에 필요한 최소 모델을 만듭니다."""

    return CatalogModel(
        id=new_id(),
        catalog_key=new_id(),
        machine_family="general_washer",
        use_type="household",
        market_region="KR",
        model_name="WA23A8375KW",
        normalized_model_name="WA23A8375KW",
        applicant_name=applicant,
        manufacturer_name=None,
        market_status="candidate",
        evidence_status="market_evidence_only",
        recommendation_status="catalog_only",
        source_url="https://example.invalid",
    )


def test_select_adapter_uses_official_company_name():
    """모델 번호 모양만 보고 제조사를 추정하지 않아야 합니다."""

    assert select_adapter(catalog_model("LG전자(주)")) == "lg"
    assert select_adapter(catalog_model("삼성전자(주)")) == "samsung"
    assert select_adapter(catalog_model(None)) is None


def test_parse_samsung_manual_html():
    """공식 AJAX의 PDF 링크와 표시 정보를 구조화해야 합니다."""

    sample = """
    <ul class="list-type-download">
      <li class="item" data-omni="11349103">
        <strong class="name">사용자 매뉴얼</strong>
        <p class="desc">
          <span class="desc-item">ver.1.0</span>
          <span class="desc-item">한국어</span>
          <span class="desc-item">2026-03-30</span>
        </p>
        <p class="box-btn">
          <a href="https://downloadcenter.samsung.com/manual.pdf"
             class="btn-download" data-nmfile="manual.pdf">다운로드</a>
        </p>
      </li>
    </ul>
    """
    documents = parse_samsung_manual_html(
        sample,
        model_name="WA23A8375KW",
        product_url="https://www.samsung.com/sec/support/model/WA23A8375KW/",
    )
    assert len(documents) == 1
    assert documents[0].source_url.endswith("manual.pdf")
    assert documents[0].media_type == "application/pdf"
    assert documents[0].language == "한국어"
    assert documents[0].matching_method == "samsung_official_exact_model_page"

