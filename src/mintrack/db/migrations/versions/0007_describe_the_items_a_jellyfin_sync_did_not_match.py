"""describe the items a jellyfin sync did not match

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19 18:00:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | collections.abc.Sequence[str] | None = "0006"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jellyfin_accounts",
        sa.Column(
            "last_sync_unmatched",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("jellyfin_accounts", "last_sync_unmatched")
