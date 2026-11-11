"""대량 세탁기 카탈로그 검색·사용법 API 응답 형식입니다."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CatalogModelRead(BaseModel):
    """검색 화면에 표시할 한국 내수 세탁기 기본정보입니다."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    catalog_key: str
    machine_family: str
    use_type: str
    market_region: str
    model_name: str
    applicant_name: str | None
    manufacturer_name: str | None
    origin_claim: str | None
    capacity_kg: float | None
    latest_registration_completed_on: date | None
    market_status: str
    evidence_status: str
    recommendation_status: str
    manual_match_status: str
    manual_checked_at: datetime | None
    source_url: str


class CatalogModelsPage(BaseModel):
    """대량 결과를 한 번에 반환하지 않는 페이지 응답입니다."""

    items: list[CatalogModelRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class CatalogCountItem(BaseModel):
    """통계의 분류명과 실제 DB 건수입니다."""

    label: str
    count: int


class CatalogStatsResponse(BaseModel):
    """모델·원본·설명서·사용법 저장 현황입니다."""

    model_total: int
    source_record_total: int
    included_record_total: int
    excluded_record_total: int
    document_total: int
    models_with_document: int
    structured_instruction_total: int
    by_manual_match_status: list[CatalogCountItem]
    by_family: list[CatalogCountItem]
    by_market_status: list[CatalogCountItem]
    by_source: list[CatalogCountItem]


class CatalogDocumentRead(BaseModel):
    """모델에 정확히 연결된 공식 설명서 링크와 처리 상태입니다."""

    id: str
    source_url: str
    title: str | None
    language: str | None
    media_type: str | None
    page_count: int | None
    retrieval_status: str
    extraction_status: str
    matching_status: str
    exact_model_match: bool
    retrieved_at: datetime | None


class CatalogUsageInstructionRead(BaseModel):
    """공식 설명서에서 구조화한 사용법 한 항목입니다."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    category: str
    title: str
    instruction_text: str
    page_number: int | None
    evidence_excerpt: str | None
    review_status: str


class CatalogModelUsageResponse(BaseModel):
    """모델 기본정보와 공식 설명서·사용법을 함께 반환합니다."""

    model: CatalogModelRead
    documents: list[CatalogDocumentRead]
    instructions: list[CatalogUsageInstructionRead]

