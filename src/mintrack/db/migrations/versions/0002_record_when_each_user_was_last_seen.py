"""record when each user was last seen

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19 01:13:31.857023+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | collections.abc.Sequence[str] | None = "0001"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True))
    # Until now the last use was read from the sessions still there.
    op.execute(
        "UPDATE users SET last_seen_at = seen.last_used_at FROM "
        "(SELECT user_id, max(last_used_at) AS last_used_at FROM sessions GROUP BY user_id) AS seen "
        "WHERE seen.user_id = users.id"
    )


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
