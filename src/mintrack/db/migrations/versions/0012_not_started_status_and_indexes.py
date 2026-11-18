"""not started status, history and notification indexes, login failures per address

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18 21:00:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | collections.abc.Sequence[str] | None = "0011"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None

STATUSES = ["watch_later", "watching", "up_to_date", "finished", "stopped", "watched"]
CHECK = "check_user_media_trackingstatus"

# Shows put aside with no episode watched were never started.
NOT_STARTED = """
    UPDATE user_media SET status = 'not_started'
    WHERE status = 'watch_later'
    AND media_id IN (SELECT id FROM media WHERE media_type = 'tv')
    AND NOT EXISTS (
        SELECT FROM watched_episodes JOIN episodes ON episodes.id = watched_episodes.episode_id
        WHERE watched_episodes.user_id = user_media.user_id AND episodes.media_id = user_media.media_id
    )
"""


def _status_check(statuses: list[str]) -> None:
    op.drop_constraint(op.f(CHECK), "user_media", type_="check")
    op.create_check_constraint(op.f(CHECK), "user_media", sa.column("status").in_(statuses))


def upgrade() -> None:
    _status_check([*STATUSES, "not_started"])
    op.execute(NOT_STARTED)
    op.create_index(
        op.f("index_watched_episodes_on_user_id_watched_at_episode_id"),
        "watched_episodes",
        ["user_id", "watched_at", "episode_id"],
    )
    op.create_index(
        op.f("index_watched_movies_on_user_id_watched_at_media_id"),
        "watched_movies",
        ["user_id", "watched_at", "media_id"],
    )
    op.create_index(op.f("index_episode_notifications_on_episode_id"), "episode_notifications", ["episode_id"])
    op.drop_index(op.f("index_login_failures_on_username_address_failed_at"), table_name="login_failures")
    op.create_index(op.f("index_login_failures_on_address_failed_at"), "login_failures", ["address", "failed_at"])


def downgrade() -> None:
    op.drop_index(op.f("index_login_failures_on_address_failed_at"), table_name="login_failures")
    op.create_index(
        op.f("index_login_failures_on_username_address_failed_at"),
        "login_failures",
        ["username", "address", "failed_at"],
    )
    op.drop_index(op.f("index_episode_notifications_on_episode_id"), table_name="episode_notifications")
    op.drop_index(op.f("index_watched_movies_on_user_id_watched_at_media_id"), table_name="watched_movies")
    op.drop_index(op.f("index_watched_episodes_on_user_id_watched_at_episode_id"), table_name="watched_episodes")
    op.execute("UPDATE user_media SET status = 'watch_later' WHERE status = 'not_started'")
    _status_check(STATUSES)
