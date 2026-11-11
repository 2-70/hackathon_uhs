"""WashWise 첫 번째 데이터베이스 스키마를 생성합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """모델과 외래 키·유일성 제약을 생성합니다."""

    # 사용자가 등록한 옷장 데이터를 저장합니다.
    op.create_table(
        "wardrobe_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("item_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("color", sa.String(length=80), nullable=True),
        sa.Column("material", sa.String(length=120), nullable=True),
        sa.Column("care_temperature_celsius", sa.Integer(), nullable=True),
        sa.Column("care_spin_level", sa.String(length=40), nullable=True),
        sa.Column("care_dry_method", sa.String(length=80), nullable=True),
        sa.Column("care_notes", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # 소유자별 목록 조회를 빠르게 합니다.
    op.create_index("ix_wardrobe_items_owner_id", "wardrobe_items", ["owner_id"])

    # 공식 제품의 기본 정보를 저장합니다.
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_key", sa.String(length=160), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("official_url", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_key"),
    )
    # 제품 필드별 관리 정보와 근거를 저장합니다.
    op.create_table(
        "product_care_instructions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("value_text", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "field_name", name="uq_product_care_field"),
    )

    # 공식 기기 모델을 저장합니다.
    op.create_table(
        "machine_models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("machine_key", sa.String(length=160), nullable=False),
        sa.Column("machine_type", sa.String(length=40), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("verified_scope", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_key"),
    )
    # 공식 기기 코스를 저장합니다.
    op.create_table(
        "machine_courses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("machine_model_id", sa.String(length=36), nullable=False),
        sa.Column("course_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["machine_model_id"], ["machine_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_model_id", "course_key", name="uq_machine_course_key"),
    )

    # 코스에서 실제로 확인된 설정 조합만 저장합니다.
    op.create_table(
        "machine_course_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("setting_key", sa.String(length=240), nullable=False),
        sa.Column("temperature_celsius", sa.Integer(), nullable=True),
        sa.Column("spin_level", sa.String(length=40), nullable=True),
        sa.Column("water_level", sa.String(length=40), nullable=True),
        sa.Column("dry_level", sa.String(length=40), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["machine_courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "setting_key", name="uq_machine_setting_key"),
    )
    # 코스별 설정 조회를 빠르게 합니다.
    op.create_index("ix_machine_settings_course", "machine_course_settings", ["course_id"])

    # 사용자가 등록한 기기와 수동 입력을 저장합니다.
    op.create_table(
        "user_machines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("machine_type", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("machine_model_id", sa.String(length=36), nullable=True),
        sa.Column("manual_input", sa.JSON(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["machine_model_id"], ["machine_models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # 소유자별 재조회에 사용할 인덱스입니다.
    op.create_index("ix_user_machines_owner_id", "user_machines", ["owner_id"])


def downgrade() -> None:
    """생성 순서의 역순으로 테이블을 제거합니다."""

    # 자식 테이블부터 제거해 외래 키 제약 충돌을 피합니다.
    op.drop_index("ix_user_machines_owner_id", table_name="user_machines")
    op.drop_table("user_machines")
    op.drop_index("ix_machine_settings_course", table_name="machine_course_settings")
    op.drop_table("machine_course_settings")
    op.drop_table("machine_courses")
    op.drop_table("machine_models")
    op.drop_table("product_care_instructions")
    op.drop_table("products")
    op.drop_index("ix_wardrobe_items_owner_id", table_name="wardrobe_items")
    op.drop_table("wardrobe_items")
