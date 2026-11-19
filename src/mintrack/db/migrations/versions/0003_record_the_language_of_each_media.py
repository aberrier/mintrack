"""record the language of each media

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19 01:54:15.976228+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | collections.abc.Sequence[str] | None = "0002"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    # Existing media get NULL, an unknown language: the next refresh pass fetches them again.
    op.add_column("media", sa.Column("language", sa.TEXT(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "language")
