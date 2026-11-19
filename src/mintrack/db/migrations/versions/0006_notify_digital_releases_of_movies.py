"""notify digital releases of movies

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19 12:59:01.197448+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | collections.abc.Sequence[str] | None = "0005"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "movie_release_notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_movie_release_notifications_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_movie_release_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_movie_release_notifications")),
    )
    op.create_index(
        op.f("index_movie_release_notifications_on_media_id"), "movie_release_notifications", ["media_id"], unique=False
    )
    op.add_column("media", sa.Column("digital_release_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "digital_release_date")
    op.drop_index(op.f("index_movie_release_notifications_on_media_id"), table_name="movie_release_notifications")
    op.drop_table("movie_release_notifications")
