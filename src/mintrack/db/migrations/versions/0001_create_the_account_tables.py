"""create the account tables

Revision ID: 0001
Revises:
Create Date: 2026-11-18 11:19:18.913645+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | collections.abc.Sequence[str] | None = None
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_failures",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("address", sa.TEXT(), nullable=False),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_failures")),
    )
    op.create_index(
        op.f("index_login_failures_on_username_address_failed_at"),
        "login_failures",
        ["username", "address", "failed_at"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("password_hash", sa.TEXT(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.TEXT(), server_default="UTC", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("link_token_hash", sa.LargeBinary(), nullable=True),
        sa.Column("link_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("link_token_hash", name=op.f("unique_users_link_token_hash")),
    )
    op.create_index("unique_users_lower_username", "users", [sa.literal_column("lower(username)")], unique=True)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("unique_sessions_token_hash")),
    )
    op.create_index(op.f("index_sessions_on_user_id"), "sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("index_sessions_on_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("unique_users_lower_username", table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("index_login_failures_on_username_address_failed_at"), table_name="login_failures")
    op.drop_table("login_failures")
