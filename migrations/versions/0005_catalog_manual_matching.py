"""모델별 공식 설명서 검색 상태를 추가합니다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_catalog_manual_matching"
down_revision: str | None = "0004_korean_washer_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 2,663개 모델을 pending으로 유지한 채 검색 상태 필드를 추가합니다."""

    with op.batch_alter_table("catalog_models") as batch:
        batch.add_column(
            sa.Column(
                "manual_match_status",
                sa.String(40),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(sa.Column("manual_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("manual_match_notes", sa.Text(), nullable=True))
        batch.create_index("ix_catalog_models_manual_status", ["manual_match_status"])


def downgrade() -> None:
    """설명서 상태 필드만 제거하고 모델·원본 데이터는 보존합니다."""

    with op.batch_alter_table("catalog_models") as batch:
        batch.drop_index("ix_catalog_models_manual_status")
        batch.drop_column("manual_match_notes")
        batch.drop_column("manual_checked_at")
        batch.drop_column("manual_match_status")

