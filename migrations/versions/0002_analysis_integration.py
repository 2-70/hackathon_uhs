"""Preserve verified catalog details, named settings, and wardrobe care fields."""

import sqlalchemy as sa
from alembic import op

revision = "0002_analysis_integration"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("catalog_details", sa.JSON(), nullable=True))
    op.add_column("product_care_instructions", sa.Column("evidence", sa.String(300), nullable=True))
    op.add_column("machine_course_settings", sa.Column("temperature_setting", sa.String(40)))
    op.add_column("machine_course_settings", sa.Column("spin_rpm", sa.Integer()))
    op.add_column("wardrobe_items", sa.Column("care_wash_method", sa.String(30)))
    op.add_column("wardrobe_items", sa.Column("care_gentle", sa.Boolean()))
    op.add_column("wardrobe_items", sa.Column("care_tumble_dry_allowed", sa.Boolean()))


def downgrade() -> None:
    op.drop_column("wardrobe_items", "care_tumble_dry_allowed")
    op.drop_column("wardrobe_items", "care_gentle")
    op.drop_column("wardrobe_items", "care_wash_method")
    op.drop_column("machine_course_settings", "spin_rpm")
    op.drop_column("machine_course_settings", "temperature_setting")
    op.drop_column("product_care_instructions", "evidence")
    op.drop_column("products", "catalog_details")
