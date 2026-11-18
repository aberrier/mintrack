"""push subscription sessions, jellyfin sync status check, api token creation default

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 09:10:00.000000+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | collections.abc.Sequence[str] | None = "0010"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("push_subscriptions", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("index_push_subscriptions_on_session_id"), "push_subscriptions", ["session_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_push_subscriptions_session_id_sessions"),
        "push_subscriptions",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("check_jellyfin_accounts_jellyfinsyncstatus"),
        "jellyfin_accounts",
        sa.column("last_sync_status").in_(["ok", "unreachable", "unauthorized", "failed"]),
    )
    op.alter_column("api_tokens", "created_at", server_default=sa.func.now())


def downgrade() -> None:
    op.alter_column("api_tokens", "created_at", server_default=None)
    op.drop_constraint(op.f("check_jellyfin_accounts_jellyfinsyncstatus"), "jellyfin_accounts", type_="check")
    op.drop_constraint(op.f("fk_push_subscriptions_session_id_sessions"), "push_subscriptions", type_="foreignkey")
    op.drop_index(op.f("index_push_subscriptions_on_session_id"), table_name="push_subscriptions")
    op.drop_column("push_subscriptions", "session_id")
