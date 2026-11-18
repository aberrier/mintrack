"""api tokens

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18 11:18:24.575553+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | collections.abc.Sequence[str] | None = "0007"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("unique_api_tokens_token_hash")),
    )
    op.create_index(op.f("index_api_tokens_on_user_id"), "api_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("index_api_tokens_on_user_id"), table_name="api_tokens")
    op.drop_table("api_tokens")
