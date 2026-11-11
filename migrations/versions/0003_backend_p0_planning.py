"""계획 엔진에 필요한 의류 근거와 기기 설정 필드를 추가합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_backend_p0_planning"
down_revision: str | None = "0002_analysis_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 행과 ID를 유지하는 nullable 중심의 추가형 변경을 수행합니다."""

    # SQLite 구조 검증에서도 외래 키 추가가 동작하도록 batch 모드를 사용합니다.
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.add_column(sa.Column("brand", sa.String(120), nullable=True))
        batch.add_column(sa.Column("product_name", sa.String(200), nullable=True))
        batch.add_column(sa.Column("product_code", sa.String(120), nullable=True))
        batch.add_column(sa.Column("matched_product_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("official_product_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("image_reference", sa.String(500), nullable=True))
        batch.add_column(sa.Column("care_wash_strength", sa.String(30), nullable=True))
        batch.add_column(sa.Column("care_max_spin_rpm", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("color_family", sa.String(20), nullable=True))
        batch.add_column(sa.Column("color_bleed_risk", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("wash_separately", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("care_tumble_dry_heat", sa.String(30), nullable=True))
        batch.add_column(sa.Column("care_natural_dry", sa.String(50), nullable=True))
        batch.add_column(sa.Column("care_dry_in_shade", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("weight_grams", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_wardrobe_items_matched_product",
            "products",
            ["matched_product_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 필드별 확인 상태와 서로 다른 출처의 충돌 값을 별도 행으로 보존합니다.
    op.create_table(
        "wardrobe_care_fields",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("wardrobe_item_id", sa.String(36), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("evidence", sa.String(500), nullable=True),
        sa.Column("knowledge_status", sa.String(30), nullable=False),
        sa.Column("conflicting_values", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["wardrobe_item_id"], ["wardrobe_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "wardrobe_item_id", "field_name", name="uq_wardrobe_care_field"
        ),
    )
    op.create_index(
        "ix_wardrobe_care_fields_item", "wardrobe_care_fields", ["wardrobe_item_id"]
    )

    # 용량을 모르는 기존 기기는 null 상태로 유지해 안전값을 추정하지 않습니다.
    with op.batch_alter_table("machine_models") as batch:
        batch.add_column(sa.Column("capacity_kg", sa.Float(), nullable=True))
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("capacity_source_url", sa.String(500), nullable=True))
        batch.add_column(
            sa.Column("capacity_verification_status", sa.String(30), nullable=True)
        )

    # 설정 한 행이 실제로 함께 선택 가능한 한 조합이라는 기존 구조를 확장합니다.
    with op.batch_alter_table("machine_course_settings") as batch:
        batch.add_column(sa.Column("wash_strength", sa.String(30), nullable=True))
        batch.add_column(
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("manual_page", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evidence", sa.String(500), nullable=True))


def downgrade() -> None:
    """로컬 구조 검증을 위해 새 필드만 역순으로 제거합니다."""

    with op.batch_alter_table("machine_course_settings") as batch:
        batch.drop_column("evidence")
        batch.drop_column("manual_page")
        batch.drop_column("is_default")
        batch.drop_column("wash_strength")

    with op.batch_alter_table("machine_models") as batch:
        batch.drop_column("capacity_verification_status")
        batch.drop_column("capacity_source_url")
        batch.drop_column("release_year")
        batch.drop_column("capacity_kg")

    op.drop_index("ix_wardrobe_care_fields_item", table_name="wardrobe_care_fields")
    op.drop_table("wardrobe_care_fields")

    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_constraint("fk_wardrobe_items_matched_product", type_="foreignkey")
        batch.drop_column("weight_grams")
        batch.drop_column("care_dry_in_shade")
        batch.drop_column("care_natural_dry")
        batch.drop_column("care_tumble_dry_heat")
        batch.drop_column("wash_separately")
        batch.drop_column("color_bleed_risk")
        batch.drop_column("color_family")
        batch.drop_column("care_max_spin_rpm")
        batch.drop_column("care_wash_strength")
        batch.drop_column("image_reference")
        batch.drop_column("official_product_url")
        batch.drop_column("matched_product_id")
        batch.drop_column("product_code")
        batch.drop_column("product_name")
        batch.drop_column("brand")
