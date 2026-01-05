from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "scan_runs",
        "universe",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "scan_runs",
        "universe",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="LEFT(universe, 255)",
    )
