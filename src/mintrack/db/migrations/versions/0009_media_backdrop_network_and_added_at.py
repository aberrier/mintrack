"""media backdrop, network and runtime, user media added at

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18 16:00:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | collections.abc.Sequence[str] | None = "0008"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("backdrop_path", sa.TEXT(), nullable=True))
    op.add_column("media", sa.Column("network", sa.TEXT(), nullable=True))
    op.add_column("media", sa.Column("runtime", sa.INTEGER(), nullable=True))
    op.add_column("user_media", sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=True))
    # The library had no addition date: the first watch, when earlier than the last activity, is the closest known.
    op.execute(
        """
        UPDATE user_media SET added_at = LEAST(
            updated_at,
            (SELECT min(w.watched_at) FROM watched_episodes w JOIN episodes e ON e.id = w.episode_id
             WHERE w.user_id = user_media.user_id AND e.media_id = user_media.media_id),
            (SELECT w.watched_at FROM watched_movies w
             WHERE w.user_id = user_media.user_id AND w.media_id = user_media.media_id)
        )
        """
    )
    op.alter_column("user_media", "added_at", nullable=False)


def downgrade() -> None:
    op.drop_column("user_media", "added_at")
    op.drop_column("media", "runtime")
    op.drop_column("media", "network")
    op.drop_column("media", "backdrop_path")
