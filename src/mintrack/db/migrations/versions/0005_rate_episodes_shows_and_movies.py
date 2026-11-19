"""rate episodes shows and movies

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19 12:59:34.163093+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | collections.abc.Sequence[str] | None = "0004"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_ratings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column("review", sa.TEXT(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(review) <= 500", name=op.f("check_media_ratings_review_length")),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name=op.f("check_media_ratings_stars")),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_media_ratings_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_media_ratings_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_media_ratings")),
    )
    op.create_index(op.f("index_media_ratings_on_media_id"), "media_ratings", ["media_id"], unique=False)
    op.create_table(
        "episode_ratings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column("review", sa.TEXT(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(review) <= 500", name=op.f("check_episode_ratings_review_length")),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name=op.f("check_episode_ratings_stars")),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["episodes.id"], name=op.f("fk_episode_ratings_episode_id_episodes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_episode_ratings_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "episode_id", name=op.f("pk_episode_ratings")),
    )
    op.create_index(op.f("index_episode_ratings_on_episode_id"), "episode_ratings", ["episode_id"], unique=False)
    # Cached media get these on their next refresh.
    op.add_column("episodes", sa.Column("overview", sa.TEXT(), server_default="", nullable=False))
    op.add_column("episodes", sa.Column("still_path", sa.TEXT(), nullable=True))
    op.add_column("episodes", sa.Column("vote_average", sa.Double(), nullable=True))
    op.add_column("episodes", sa.Column("vote_count", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("vote_average", sa.Double(), nullable=True))
    op.add_column("media", sa.Column("vote_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "vote_count")
    op.drop_column("media", "vote_average")
    op.drop_column("episodes", "vote_count")
    op.drop_column("episodes", "vote_average")
    op.drop_column("episodes", "still_path")
    op.drop_column("episodes", "overview")
    op.drop_index(op.f("index_episode_ratings_on_episode_id"), table_name="episode_ratings")
    op.drop_table("episode_ratings")
    op.drop_index(op.f("index_media_ratings_on_media_id"), table_name="media_ratings")
    op.drop_table("media_ratings")
