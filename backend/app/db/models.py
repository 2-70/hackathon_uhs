"""WashWise의 영속 데이터 모델입니다."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def new_id() -> str:
    """SQLite와 PostgreSQL에서 동일하게 사용할 문자열 UUID를 생성합니다."""

    # 문자열 UUID는 두 데이터베이스에서 같은 API 형식으로 직렬화할 수 있습니다.
    return str(uuid4())


def utc_now() -> datetime:
    """저장 시점이 서버 지역 시간에 의존하지 않도록 UTC를 반환합니다."""

    # timezone 정보가 포함된 시각을 사용해 여러 지역의 앱이 같은 기준을 보게 합니다.
    return datetime.now(UTC)


class TimestampMixin:
    """생성·수정 시각을 공통으로 제공하는 믹스인입니다."""

    # 생성 시각은 레코드가 처음 저장될 때 자동으로 채웁니다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    # 수정 시각은 API가 값을 변경할 때 라우터에서 새로 기록합니다.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WardrobeItem(TimestampMixin, Base):
    """사용자가 등록한 의류와 세탁 정보입니다."""

    # API에서 노출할 안정적인 레코드 식별자입니다.
    __tablename__ = "wardrobe_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 현재 데모에서는 고정값이지만 이후 인증 사용자와 연결할 소유자 키입니다.
    owner_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # 사용자가 목록에서 알아보기 위한 의류 이름입니다.
    item_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 셔츠·바지 등 의류 분류는 선택 입력으로 둡니다.
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 색상과 소재는 모르는 경우 null로 보존합니다.
    color: Mapped[str | None] = mapped_column(String(80), nullable=True)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 상품 참조는 사용자가 입력한 표시 정보와 공용 카탈로그 연결을 함께 보존합니다.
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    matched_product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    official_product_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 실제 사진 파일 대신 모바일이나 저장소가 관리하는 불투명 참조값만 저장합니다.
    image_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # AI 통합 migration에서 먼저 추가되는 하위호환 세탁 필드입니다.
    care_wash_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    care_gentle: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 확인된 온도·탈수·건조 정보만 각각 저장하고 모르면 null로 둡니다.
    care_temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    care_wash_strength: Mapped[str | None] = mapped_column(String(30), nullable=True)
    care_max_spin_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    care_spin_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    care_dry_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 색상 분리와 단독 세탁 여부는 계획 그룹을 나눌 때 사용합니다.
    color_family: Mapped[str | None] = mapped_column(String(20), nullable=True)
    color_bleed_risk: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wash_separately: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 건조 필드는 세탁 계획 응답의 의류별 안내에 사용합니다.
    care_tumble_dry_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    care_tumble_dry_heat: Mapped[str | None] = mapped_column(String(30), nullable=True)
    care_natural_dry: Mapped[str | None] = mapped_column(String(50), nullable=True)
    care_dry_in_shade: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 무게와 기기 용량을 모두 아는 경우에만 용량 검증을 수행합니다.
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 자유로운 주의사항은 원문을 잃지 않기 위해 문자열로 저장합니다.
    care_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 값이 어디에서 왔는지 구분해 AI 추정값과 사용자 입력을 섞지 않습니다.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="user_input")
    # confirmed와 unconfirmed를 구분해 앱이 사용자 확인이 필요한 값을 알 수 있게 합니다.
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unconfirmed"
    )
    # 출처 URL이나 라벨 메모처럼 선택적인 근거를 저장합니다.
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 필드별 출처와 충돌을 함께 읽을 수 있도록 자식 행을 연결합니다.
    care_fields: Mapped[list["WardrobeCareField"]] = relationship(
        back_populates="wardrobe_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    matched_product: Mapped["Product | None"] = relationship(
        foreign_keys=[matched_product_id]
    )

    @property
    def product_reference(self) -> dict[str, str | None] | None:
        """응답에서 중첩된 상품 참조 형태를 제공하는 읽기 전용 값입니다."""

        # 상품 관련 값이 하나도 없으면 기존 API처럼 null을 반환합니다.
        values = {
            "brand": self.brand,
            "product_name": self.product_name,
            "product_code": self.product_code,
            "matched_product_id": self.matched_product_id,
            "official_url": self.official_product_url,
        }
        return values if any(value is not None for value in values.values()) else None


class WardrobeCareField(Base):
    """의류 관리 조건 한 필드의 값·출처·확인 상태를 보존합니다."""

    __tablename__ = "wardrobe_care_fields"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wardrobe_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wardrobe_items.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # JSON을 사용해 숫자·불리언·문자열 값을 형 변환 없이 보존합니다.
    value_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    knowledge_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 실제 출처 충돌은 하나를 선택하지 않고 모든 후보와 근거를 배열로 저장합니다.
    conflicting_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "wardrobe_item_id", "field_name", name="uq_wardrobe_care_field"
        ),
        Index("ix_wardrobe_care_fields_item", "wardrobe_item_id"),
    )
    wardrobe_item: Mapped[WardrobeItem] = relationship(back_populates="care_fields")


class Product(TimestampMixin, Base):
    """공식 제품 카탈로그의 기본 정보입니다."""

    __tablename__ = "products"
    # 내부 조인용 식별자는 시드가 제공하지 않아도 서버가 생성합니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 반복 로딩 시 같은 제품을 찾는 안정적인 외부 식별자입니다.
    product_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    # 제품 표시에 필요한 브랜드와 모델명입니다.
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 공식 문서의 위치를 기록하되 비밀정보는 저장하지 않습니다.
    official_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # AI 상품 매칭에 필요한 비정형 표시 정보는 검증된 JSON 그대로 보존합니다.
    catalog_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 제품 정보의 출처 유형과 확인 상태를 함께 보관합니다.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 제품 삭제 시 하위 관리 정보도 함께 삭제되어 고아 데이터를 막습니다.
    care_instructions: Mapped[list["ProductCareInstruction"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


class ProductCareInstruction(Base):
    """제품의 필드별 세탁 지침과 근거입니다."""

    __tablename__ = "product_care_instructions"
    # 제품 관리 정보도 독립 ID를 가져 특정 필드만 갱신할 수 있게 합니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 제품 삭제 시 연결된 지침을 함께 정리합니다.
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    # wash_temperature_celsius 같은 필드 이름을 저장합니다.
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 원래 값의 표현을 보존해 숫자·문자·범위 모두 담을 수 있게 합니다.
    value_text: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # 필드별 출처와 확인 상태는 제품 기본 정보와 별도로 추적합니다.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 같은 제품의 같은 필드는 한 번만 존재하게 해 반복 시드의 중복을 막습니다.
    __table_args__ = (UniqueConstraint("product_id", "field_name", name="uq_product_care_field"),)
    # ORM에서 제품을 역방향으로 확인할 수 있도록 관계를 연결합니다.
    product: Mapped[Product] = relationship(back_populates="care_instructions")


class MachineModel(TimestampMixin, Base):
    """공식 세탁기 모델과 확인 범위입니다."""

    __tablename__ = "machine_models"
    # 앱에서 참조할 내부 식별자입니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 같은 공식 모델을 다시 찾기 위한 시드 고유 키입니다.
    machine_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    # washer·dryer 같은 기기 종류를 저장합니다.
    machine_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # 제조사·모델명과 공식 출처를 보관합니다.
    manufacturer: Mapped[str] = mapped_column(String(120), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    verified_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 용량은 공식 근거가 있을 때만 채우며 모르면 null로 둡니다.
    capacity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    capacity_verification_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 모델 조회 시 확인된 코스와 조합을 함께 가져오기 위한 관계입니다.
    courses: Mapped[list["MachineCourse"]] = relationship(
        back_populates="machine_model", cascade="all, delete-orphan", passive_deletes=True
    )


class CatalogSource(TimestampMixin, Base):
    """한국 내수 세탁기 카탈로그를 제공한 공식 자료원입니다."""

    __tablename__ = "catalog_sources"
    # 내부 조인용 ID와 사람이 읽을 수 있는 안정적인 자료원 키를 함께 둡니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    # 기관명과 자료 이름을 분리해 같은 기관의 현행·구기자재 목록을 구분합니다.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    authority: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="KR")
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # 수집 당시 공식 화면에 표시된 총건수는 실제 수집 건수와 별도로 보존합니다.
    reported_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogModel(TimestampMixin, Base):
    """한국시장 근거가 발견된 세탁기 모델의 검색용 기본정보입니다."""

    __tablename__ = "catalog_models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 해시 기반 키는 긴 모델명을 자르지 않고 반복 적재에서도 같은 ID를 찾게 합니다.
    catalog_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    machine_family: Mapped[str] = mapped_column(String(40), nullable=False)
    use_type: Mapped[str] = mapped_column(String(30), nullable=False, default="household")
    market_region: Mapped[str] = mapped_column(String(20), nullable=False, default="KR")
    # 원문 모델명과 검색용 정규화 값을 분리해 접미사·기호를 잃지 않습니다.
    model_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_model_name: Mapped[str] = mapped_column(String(500), nullable=False)
    applicant_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    manufacturer_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origin_claim: Mapped[str | None] = mapped_column(String(40), nullable=True)
    capacity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_registration_completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 등록 목록만으로 실제 판매를 단정하지 않고 후보·근거·추천 상태를 각각 저장합니다.
    market_status: Mapped[str] = mapped_column(String(30), nullable=False, default="candidate")
    evidence_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="market_evidence_only"
    )
    recommendation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="catalog_only"
    )
    # 설명서 검색 시도와 결과를 모델별로 남겨 미확인을 완료로 오해하지 않게 합니다.
    manual_match_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending"
    )
    manual_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    manual_match_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    __table_args__ = (
        Index("ix_catalog_models_name", "normalized_model_name"),
        Index("ix_catalog_models_family", "machine_family"),
        Index("ix_catalog_models_market_status", "market_status"),
        Index("ix_catalog_models_manual_status", "manual_match_status"),
    )


class CatalogIngestionRun(Base):
    """자료원 한 개의 수집 실행과 재개 체크포인트입니다."""

    __tablename__ = "catalog_ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 체크포인트 JSON은 완료 단계와 다음 재시작 지점을 사람이 확인할 수 있게 합니다.
    checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_catalog_runs_source_started", "source_id", "started_at"),)


class CatalogSourceRecord(Base):
    """공식 목록의 원본 행과 기간 판정 결과입니다."""

    __tablename__ = "catalog_source_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_sources.id", ondelete="CASCADE"), nullable=False
    )
    catalog_model_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_models.id", ondelete="SET NULL"), nullable=True
    )
    # 자료원 내부 키는 행 순서가 바뀌어도 같은 신고 행을 다시 찾도록 내용에서 만듭니다.
    source_record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    model_name_raw: Mapped[str] = mapped_column(String(500), nullable=False)
    applicant_name_raw: Mapped[str | None] = mapped_column(String(300), nullable=True)
    manufacturer_name_raw: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origin_claim_raw: Mapped[str | None] = mapped_column(String(40), nullable=True)
    capacity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_grade_raw: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eligibility_status: Mapped[str] = mapped_column(String(30), nullable=False)
    eligibility_reason: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_key", name="uq_catalog_source_record"),
        Index("ix_catalog_records_model", "catalog_model_id"),
        Index("ix_catalog_records_eligibility", "eligibility_status"),
    )


class CatalogDocument(TimestampMixin, Base):
    """공식 사용설명서와 추출 상태를 문서 해시 단위로 보존합니다."""

    __tablename__ = "catalog_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_status: Mapped[str] = mapped_column(String(30), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(30), nullable=False)
    model_scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CatalogModelDocument(Base):
    """정확한 모델과 공식 설명서의 적용 관계입니다."""

    __tablename__ = "catalog_model_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    catalog_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_models.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_documents.id", ondelete="CASCADE"), nullable=False
    )
    matching_method: Mapped[str] = mapped_column(String(50), nullable=False)
    matching_status: Mapped[str] = mapped_column(String(30), nullable=False)
    exact_model_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (
        UniqueConstraint("catalog_model_id", "document_id", name="uq_catalog_model_document"),
    )


class CatalogUsageInstruction(Base):
    """설명서에서 확인한 모델별 사용법 한 항목입니다."""

    __tablename__ = "catalog_usage_instructions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    catalog_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_models.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_documents.id", ondelete="CASCADE"), nullable=False
    )
    instruction_key: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instruction_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 짧은 근거만 저장해 공식 원문 전체를 불필요하게 재배포하지 않습니다.
    evidence_excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "catalog_model_id", "document_id", "instruction_key", name="uq_catalog_usage_item"
        ),
        Index("ix_catalog_usage_model", "catalog_model_id"),
    )


class MachineCourse(Base):
    """공식 기기에서 확인된 세탁 코스입니다."""

    __tablename__ = "machine_courses"
    # 코스 단위의 내부 식별자입니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 모델이 삭제될 때 하위 코스도 삭제합니다.
    machine_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("machine_models.id", ondelete="CASCADE"), nullable=False
    )
    # 시드에서 코스를 안정적으로 갱신하기 위한 키입니다.
    course_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 코스별로 확인된 설정 조합만 저장합니다.
    settings: Mapped[list["MachineCourseSetting"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", passive_deletes=True
    )
    # 한 모델 안에서 course_key가 중복되지 않도록 제한합니다.
    __table_args__ = (
        UniqueConstraint("machine_model_id", "course_key", name="uq_machine_course_key"),
    )
    # ORM에서 부모 모델을 확인하기 위한 관계입니다.
    machine_model: Mapped[MachineModel] = relationship(back_populates="courses")


class MachineCourseSetting(Base):
    """특정 코스에서 실제로 확인된 설정 조합 한 건입니다."""

    __tablename__ = "machine_course_settings"
    # 조합을 독립 레코드로 저장해 확인되지 않은 조합을 자동 생성하지 않습니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 코스 삭제 시 설정도 함께 삭제합니다.
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("machine_courses.id", ondelete="CASCADE"), nullable=False
    )
    # 여러 nullable 값이 있는 DB에서도 중복을 막기 위한 정규화 키입니다.
    setting_key: Mapped[str] = mapped_column(String(240), nullable=False)
    # 실제 지원 여부를 설명하는 세탁기 설정 값입니다.
    temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 설명서의 Cold/Warm 같은 이름은 근거 없이 섭씨로 바꾸지 않고 별도 저장합니다.
    temperature_setting: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wash_strength: Mapped[str | None] = mapped_column(String(30), nullable=True)
    spin_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    spin_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    water_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dry_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 설정 단위의 출처와 확인 상태를 보관합니다.
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 같은 코스에 동일한 정규화 조합을 한 번만 저장합니다.
    __table_args__ = (
        UniqueConstraint("course_id", "setting_key", name="uq_machine_setting_key"),
        Index("ix_machine_settings_course", "course_id"),
    )
    # ORM에서 부모 코스를 확인하기 위한 관계입니다.
    course: Mapped[MachineCourse] = relationship(back_populates="settings")


class UserMachine(TimestampMixin, Base):
    """사용자가 실제로 등록한 기기입니다."""

    __tablename__ = "user_machines"
    # 앱이 재실행되어도 같은 등록 레코드를 찾는 ID입니다.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # 데모 사용자 또는 이후 인증 사용자와 연결할 소유자입니다.
    owner_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # 사용자 기기의 종류는 공용 모델과 비교할 때 사용합니다.
    machine_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # 앱에 표시할 사용자 지정 이름입니다.
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 공용 모델을 선택한 경우에만 값이 있고 수동 등록은 null입니다.
    machine_model_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("machine_models.id", ondelete="SET NULL"), nullable=True
    )
    # 수동 입력은 공용 모델 데이터를 덮어쓰지 않고 이 등록에만 귀속됩니다.
    manual_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 사용자가 남긴 추가 메모입니다.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 공용 모델을 응답에 포함하기 위한 선택적 관계입니다.
    machine_model: Mapped[MachineModel | None] = relationship()
