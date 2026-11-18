"""jellyfin accounts

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18 11:21:20.751595+00:00

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
        "jellyfin_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("server_url", sa.TEXT(), nullable=False),
        sa.Column("server_id", sa.TEXT(), nullable=False),
        sa.Column("jellyfin_user_id", sa.TEXT(), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("token", sa.TEXT(), nullable=False),
        sa.Column("synced_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "last_sync_status",
            sa.Enum(
                "ok", "unreachable", "unauthorized", "failed", name="jellyfinsyncstatus", native_enum=False, length=20
            ),
            nullable=True,
        ),
        sa.Column("last_sync_imported", sa.Integer(), nullable=False),
        sa.Column("last_sync_skipped", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_jellyfin_accounts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jellyfin_accounts")),
        sa.UniqueConstraint(
            "user_id",
            "server_id",
            "jellyfin_user_id",
            name=op.f("unique_jellyfin_accounts_user_id_server_id_jellyfin_user_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("jellyfin_accounts")
