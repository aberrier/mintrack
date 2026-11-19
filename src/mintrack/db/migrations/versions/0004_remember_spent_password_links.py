"""remember spent password links

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19 12:38:26.069872+00:00

"""

import collections.abc

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | collections.abc.Sequence[str] | None = "0003"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spent_password_links",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum("used", "replaced", name="spentlinkreason", native_enum=False, create_constraint=True, length=None),
            nullable=False,
        ),
        sa.Column("spent_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_spent_password_links_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_spent_password_links")),
    )
    op.create_index(op.f("index_spent_password_links_on_user_id"), "spent_password_links", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("index_spent_password_links_on_user_id"), table_name="spent_password_links")
    op.drop_table("spent_password_links")
