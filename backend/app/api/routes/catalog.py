"""한국 내수 세탁기 대량 카탈로그 검색과 사용법 조회 API입니다."""

from math import ceil

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from backend.app.api.deps import DbSession
from backend.app.api.schemas import COMMON_ERROR_RESPONSES
from backend.app.catalog_ingest.kea import normalize_model_name
from backend.app.catalog_ingest.schemas import (
    CatalogCountItem,
    CatalogDocumentRead,
    CatalogModelRead,
    CatalogModelsPage,
    CatalogModelUsageResponse,
    CatalogStatsResponse,
    CatalogUsageInstructionRead,
)
from backend.app.core.errors import ApiError
from backend.app.db.models import (
    CatalogDocument,
    CatalogModel,
    CatalogModelDocument,
    CatalogSource,
    CatalogSourceRecord,
    CatalogUsageInstruction,
)

router = APIRouter(
    prefix="/api/catalog",
    tags=["washer-catalog"],
    responses=COMMON_ERROR_RESPONSES,
)


@router.get("/models", response_model=CatalogModelsPage, summary="한국 내수 세탁기 검색")
def list_catalog_models(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    query: str | None = Query(default=None, min_length=1, max_length=100),
    machine_family: str | None = Query(default=None, max_length=40),
    market_status: str | None = Query(default=None, max_length=30),
    recommendation_status: str | None = Query(default=None, max_length=40),
    manufacturer: str | None = Query(default=None, max_length=100),
) -> CatalogModelsPage:
    """모델명·업체·제조원과 확인 상태를 필터링해 페이지로 반환합니다."""

    conditions = []
    if query:
        # 원문 표시명과 공백을 제거한 검색 키를 모두 조회해 사용자의 입력 차이를 흡수합니다.
        text_pattern = f"%{query}%"
        normalized_pattern = f"%{normalize_model_name(query)}%"
        conditions.append(
            or_(
                CatalogModel.model_name.ilike(text_pattern),
                CatalogModel.normalized_model_name.ilike(normalized_pattern),
                CatalogModel.applicant_name.ilike(text_pattern),
                CatalogModel.manufacturer_name.ilike(text_pattern),
            )
        )
    if machine_family:
        conditions.append(CatalogModel.machine_family == machine_family)
    if market_status:
        conditions.append(CatalogModel.market_status == market_status)
    if recommendation_status:
        conditions.append(CatalogModel.recommendation_status == recommendation_status)
    if manufacturer:
        manufacturer_pattern = f"%{manufacturer}%"
        conditions.append(
            or_(
                CatalogModel.applicant_name.ilike(manufacturer_pattern),
                CatalogModel.manufacturer_name.ilike(manufacturer_pattern),
            )
        )
    # 목록과 count가 같은 조건을 사용해야 빈 페이지나 잘못된 총건수를 만들지 않습니다.
    count_statement = select(func.count()).select_from(CatalogModel)
    item_statement = select(CatalogModel)
    if conditions:
        count_statement = count_statement.where(*conditions)
        item_statement = item_statement.where(*conditions)
    total = int(db.scalar(count_statement) or 0)
    item_statement = (
        item_statement.order_by(CatalogModel.model_name, CatalogModel.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [CatalogModelRead.model_validate(item) for item in db.scalars(item_statement)]
    return CatalogModelsPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _group_counts(db: DbSession, label_column, count_column=None) -> list[CatalogCountItem]:
    """그룹 통계를 API에서 반복하지 않도록 공통 형식으로 변환합니다."""

    target = count_column if count_column is not None else label_column
    statement = (
        select(label_column, func.count(target))
        .group_by(label_column)
        .order_by(func.count(target).desc(), label_column)
    )
    return [CatalogCountItem(label=str(label), count=int(count)) for label, count in db.execute(statement)]


@router.get("/stats", response_model=CatalogStatsResponse, summary="카탈로그 적재 통계")
def get_catalog_stats(db: DbSession) -> CatalogStatsResponse:
    """실제 DB에 저장된 모델·근거·설명서·사용법 건수를 반환합니다."""

    model_total = int(db.scalar(select(func.count()).select_from(CatalogModel)) or 0)
    source_record_total = int(
        db.scalar(select(func.count()).select_from(CatalogSourceRecord)) or 0
    )
    included_record_total = int(
        db.scalar(
            select(func.count())
            .select_from(CatalogSourceRecord)
            .where(CatalogSourceRecord.eligibility_status != "excluded")
        )
        or 0
    )
    excluded_record_total = source_record_total - included_record_total
    document_total = int(db.scalar(select(func.count()).select_from(CatalogDocument)) or 0)
    models_with_document = int(
        db.scalar(
            select(func.count(func.distinct(CatalogModelDocument.catalog_model_id))).select_from(
                CatalogModelDocument
            )
        )
        or 0
    )
    instruction_total = int(
        db.scalar(select(func.count()).select_from(CatalogUsageInstruction)) or 0
    )
    # 자료원별로는 원본 행 수를 세어 현행·구기자재 처리 범위를 확인합니다.
    source_statement = (
        select(CatalogSource.source_key, func.count(CatalogSourceRecord.id))
        .outerjoin(CatalogSourceRecord, CatalogSourceRecord.source_id == CatalogSource.id)
        .group_by(CatalogSource.source_key)
        .order_by(func.count(CatalogSourceRecord.id).desc(), CatalogSource.source_key)
    )
    by_source = [
        CatalogCountItem(label=source_key, count=int(count))
        for source_key, count in db.execute(source_statement)
    ]
    return CatalogStatsResponse(
        model_total=model_total,
        source_record_total=source_record_total,
        included_record_total=included_record_total,
        excluded_record_total=excluded_record_total,
        document_total=document_total,
        models_with_document=models_with_document,
        structured_instruction_total=instruction_total,
        by_manual_match_status=_group_counts(
            db, CatalogModel.manual_match_status, CatalogModel.id
        ),
        by_family=_group_counts(db, CatalogModel.machine_family, CatalogModel.id),
        by_market_status=_group_counts(db, CatalogModel.market_status, CatalogModel.id),
        by_source=by_source,
    )


@router.get(
    "/models/{model_id}/usage",
    response_model=CatalogModelUsageResponse,
    summary="세탁기 공식 설명서와 구조화 사용법 조회",
)
def get_catalog_model_usage(model_id: str, db: DbSession) -> CatalogModelUsageResponse:
    """정확한 모델에 연결된 공식 문서와 검토 상태가 있는 사용법만 반환합니다."""

    model = db.get(CatalogModel, model_id)
    if model is None:
        raise ApiError("CATALOG_MODEL_NOT_FOUND", "카탈로그 모델을 찾을 수 없습니다.", 404)
    document_statement = (
        select(CatalogDocument, CatalogModelDocument)
        .join(CatalogModelDocument, CatalogModelDocument.document_id == CatalogDocument.id)
        .where(CatalogModelDocument.catalog_model_id == model_id)
        .order_by(CatalogDocument.title, CatalogDocument.id)
    )
    documents = [
        CatalogDocumentRead(
            id=document.id,
            source_url=document.source_url,
            title=document.title,
            language=document.language,
            media_type=document.media_type,
            page_count=document.page_count,
            retrieval_status=document.retrieval_status,
            extraction_status=document.extraction_status,
            matching_status=link.matching_status,
            exact_model_match=link.exact_model_match,
            retrieved_at=document.retrieved_at,
        )
        for document, link in db.execute(document_statement)
    ]
    instruction_statement = (
        select(CatalogUsageInstruction)
        .where(CatalogUsageInstruction.catalog_model_id == model_id)
        .order_by(
            CatalogUsageInstruction.category,
            CatalogUsageInstruction.page_number,
            CatalogUsageInstruction.id,
        )
    )
    instructions = [
        CatalogUsageInstructionRead.model_validate(item)
        for item in db.scalars(instruction_statement)
    ]
    return CatalogModelUsageResponse(
        model=CatalogModelRead.model_validate(model),
        documents=documents,
        instructions=instructions,
    )

