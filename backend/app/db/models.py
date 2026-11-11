"""WashWise의 영속 데이터 모델입니다."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
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
    # 확인된 온도·탈수·건조 정보만 각각 저장하고 모르면 null로 둡니다.
    care_temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    care_spin_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    care_dry_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
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
    # 모델 조회 시 확인된 코스와 조합을 함께 가져오기 위한 관계입니다.
    courses: Mapped[list["MachineCourse"]] = relationship(
        back_populates="machine_model", cascade="all, delete-orphan", passive_deletes=True
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
    spin_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    water_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dry_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 설정 단위의 출처와 확인 상태를 보관합니다.
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
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
