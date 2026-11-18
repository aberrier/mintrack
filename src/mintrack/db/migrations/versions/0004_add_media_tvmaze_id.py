"""add media tvmaze id

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18 11:19:42.229870+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | collections.abc.Sequence[str] | None = "0003"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("tvmaze_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "tvmaze_id")
