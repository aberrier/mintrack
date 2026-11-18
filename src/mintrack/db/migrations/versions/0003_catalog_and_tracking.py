"""catalog and tracking

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 11:18:57.927995+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | collections.abc.Sequence[str] | None = "0002"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("movie", "tv", name="mediatype", native_enum=False, create_constraint=True, length=None),
            nullable=False,
        ),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.Column("overview", sa.TEXT(), nullable=False),
        sa.Column("poster_path", sa.TEXT(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("tmdb_status", sa.TEXT(), nullable=True),
        sa.Column("tvdb_id", sa.Integer(), nullable=True),
        sa.Column("refreshed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("media_type", "tmdb_id", name=op.f("unique_media_media_type_tmdb_id")),
    )
    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("airstamp", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_episodes_media_id_media"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_episodes")),
        sa.UniqueConstraint(
            "media_id",
            "season_number",
            "episode_number",
            name=op.f("unique_episodes_media_id_season_number_episode_number"),
        ),
    )
    op.create_table(
        "seasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], name=op.f("fk_seasons_media_id_media"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint("media_id", "season_number", name=op.f("unique_seasons_media_id_season_number")),
    )
    op.create_table(
        "user_media",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "watch_later",
                "watching",
                "up_to_date",
                "finished",
                "stopped",
                "watched",
                name="trackingstatus",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_user_media_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_media_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_user_media")),
    )
    op.create_index(op.f("index_user_media_on_media_id"), "user_media", ["media_id"], unique=False)
    op.create_table(
        "watched_movies",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("watched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_watched_movies_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_watched_movies_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_watched_movies")),
    )
    op.create_table(
        "watched_episodes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("watched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["episodes.id"], name=op.f("fk_watched_episodes_episode_id_episodes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_watched_episodes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "episode_id", name=op.f("pk_watched_episodes")),
    )
    op.create_index(op.f("index_watched_episodes_on_episode_id"), "watched_episodes", ["episode_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("index_watched_episodes_on_episode_id"), table_name="watched_episodes")
    op.drop_table("watched_episodes")
    op.drop_table("watched_movies")
    op.drop_index(op.f("index_user_media_on_media_id"), table_name="user_media")
    op.drop_table("user_media")
    op.drop_table("seasons")
    op.drop_table("episodes")
    op.drop_table("media")
