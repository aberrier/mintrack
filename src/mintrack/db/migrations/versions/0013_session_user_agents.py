"""session user agents

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-19 09:00:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | collections.abc.Sequence[str] | None = "0012"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("user_agent", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "user_agent")
