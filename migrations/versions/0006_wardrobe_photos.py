"""의류와 세탁 라벨 사진을 옷장에 저장합니다."""

import sqlalchemy as sa
from alembic import op

revision = "0006_wardrobe_photos"
down_revision = "0005_catalog_manual_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wardrobe_items", sa.Column("clothing_photo", sa.LargeBinary(), nullable=True))
    op.add_column("wardrobe_items", sa.Column("label_photo", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_column("label_photo")
        batch.drop_column("clothing_photo")
