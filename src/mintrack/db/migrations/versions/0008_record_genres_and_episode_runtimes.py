"""record genres and episode runtimes

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19 12:00:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | collections.abc.Sequence[str] | None = "0007"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("genres", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("episodes", sa.Column("runtime", sa.Integer(), nullable=True))
    # Existing media get them once fetched again: the next refresh pass takes those older than its period.
    op.execute("UPDATE media SET refreshed_at = 'epoch'")


def downgrade() -> None:
    op.drop_column("episodes", "runtime")
    op.drop_column("media", "genres")
