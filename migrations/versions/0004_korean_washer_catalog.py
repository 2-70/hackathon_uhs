"""한국 내수 세탁기 카탈로그와 공식 사용법 저장 구조를 추가합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_korean_washer_catalog"
down_revision: str | None = "0003_backend_p0_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 추천 데이터는 건드리지 않고 별도 카탈로그 테이블만 추가합니다."""

    # 같은 기관의 현행·구기자재 목록을 각각 추적할 공식 자료원 테이블입니다.
    op.create_table(
        "catalog_sources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("authority", sa.String(200), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("reported_count", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )

    # 기존 machine_models는 추천 가능한 모델만 유지하고 대량 검색 모델은 분리합니다.
    op.create_table(
        "catalog_models",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("catalog_key", sa.String(120), nullable=False),
        sa.Column("machine_family", sa.String(40), nullable=False),
        sa.Column("use_type", sa.String(30), nullable=False),
        sa.Column("market_region", sa.String(20), nullable=False),
        sa.Column("model_name", sa.String(500), nullable=False),
        sa.Column("normalized_model_name", sa.String(500), nullable=False),
        sa.Column("applicant_name", sa.String(300), nullable=True),
        sa.Column("manufacturer_name", sa.String(300), nullable=True),
        sa.Column("origin_claim", sa.String(40), nullable=True),
        sa.Column("capacity_kg", sa.Float(), nullable=True),
        sa.Column("latest_registration_completed_on", sa.Date(), nullable=True),
        sa.Column("market_status", sa.String(30), nullable=False),
        sa.Column("evidence_status", sa.String(40), nullable=False),
        sa.Column("recommendation_status", sa.String(40), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_key"),
    )
    op.create_index("ix_catalog_models_name", "catalog_models", ["normalized_model_name"])
    op.create_index("ix_catalog_models_family", "catalog_models", ["machine_family"])
    op.create_index(
        "ix_catalog_models_market_status", "catalog_models", ["market_status"]
    )

    # 실행 단위 통계와 체크포인트는 중단 뒤 자료원 단위 재개에 사용합니다.
    op.create_table(
        "catalog_ingestion_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("included_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("model_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_runs_source_started",
        "catalog_ingestion_runs",
        ["source_id", "started_at"],
    )

    # 기간 밖 행도 삭제하지 않고 판정 사유와 함께 원본 레코드로 보존합니다.
    op.create_table(
        "catalog_source_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("catalog_model_id", sa.String(36), nullable=True),
        sa.Column("source_record_key", sa.String(64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("model_name_raw", sa.String(500), nullable=False),
        sa.Column("applicant_name_raw", sa.String(300), nullable=True),
        sa.Column("manufacturer_name_raw", sa.String(300), nullable=True),
        sa.Column("origin_claim_raw", sa.String(40), nullable=True),
        sa.Column("capacity_kg", sa.Float(), nullable=True),
        sa.Column("efficiency_grade_raw", sa.String(40), nullable=True),
        sa.Column("eligibility_status", sa.String(30), nullable=False),
        sa.Column("eligibility_reason", sa.String(300), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_model_id"], ["catalog_models.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "source_record_key", name="uq_catalog_source_record"),
    )
    op.create_index("ix_catalog_records_model", "catalog_source_records", ["catalog_model_id"])
    op.create_index(
        "ix_catalog_records_eligibility", "catalog_source_records", ["eligibility_status"]
    )

    # 설명서 원문 전체 대신 공식 URL·해시·추출 상태를 문서 단위로 저장합니다.
    op.create_table(
        "catalog_documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_key", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("language", sa.String(30), nullable=True),
        sa.Column("media_type", sa.String(100), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("retrieval_status", sa.String(30), nullable=False),
        sa.Column("extraction_status", sa.String(30), nullable=False),
        sa.Column("model_scope_text", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_key"),
    )
    op.create_index(
        "ix_catalog_documents_content_sha256", "catalog_documents", ["content_sha256"]
    )

    # 모델과 설명서가 정확히 연결됐는지 별도로 기록해 가족 모델 추정을 막습니다.
    op.create_table(
        "catalog_model_documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("catalog_model_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("matching_method", sa.String(50), nullable=False),
        sa.Column("matching_status", sa.String(30), nullable=False),
        sa.Column("exact_model_match", sa.Boolean(), nullable=False),
        sa.Column("evidence", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalog_model_id"], ["catalog_models.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["catalog_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_model_id", "document_id", name="uq_catalog_model_document"
        ),
    )

    # 확인된 시작·세제·코스·옵션·주의·관리 방법만 짧은 구조화 사실로 저장합니다.
    op.create_table(
        "catalog_usage_instructions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("catalog_model_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("instruction_key", sa.String(64), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("instruction_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.String(500), nullable=True),
        sa.Column("review_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_model_id"], ["catalog_models.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["catalog_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_model_id",
            "document_id",
            "instruction_key",
            name="uq_catalog_usage_item",
        ),
    )
    op.create_index(
        "ix_catalog_usage_model", "catalog_usage_instructions", ["catalog_model_id"]
    )


def downgrade() -> None:
    """새 카탈로그 구조만 역순으로 제거해 기존 P0 데이터는 보존합니다."""

    op.drop_index("ix_catalog_usage_model", table_name="catalog_usage_instructions")
    op.drop_table("catalog_usage_instructions")
    op.drop_table("catalog_model_documents")
    op.drop_index("ix_catalog_documents_content_sha256", table_name="catalog_documents")
    op.drop_table("catalog_documents")
    op.drop_index("ix_catalog_records_eligibility", table_name="catalog_source_records")
    op.drop_index("ix_catalog_records_model", table_name="catalog_source_records")
    op.drop_table("catalog_source_records")
    op.drop_index("ix_catalog_runs_source_started", table_name="catalog_ingestion_runs")
    op.drop_table("catalog_ingestion_runs")
    op.drop_index("ix_catalog_models_market_status", table_name="catalog_models")
    op.drop_index("ix_catalog_models_family", table_name="catalog_models")
    op.drop_index("ix_catalog_models_name", table_name="catalog_models")
    op.drop_table("catalog_models")
    op.drop_table("catalog_sources")
