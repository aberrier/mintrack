"""procrastinate

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18 12:00:01.000000+00:00

"""

import collections.abc
import pathlib

from alembic import op

revision: str = "0002"
down_revision: str | collections.abc.Sequence[str] | None = "0001"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None

SCHEMA = pathlib.Path(__file__).parent.parent / "procrastinate" / "schema-3.11.0.sql"

DROP_PROCRASTINATE = r"""
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = current_schema()
            AND tablename LIKE 'procrastinate\_%' LOOP
        EXECUTE format('DROP TABLE %I CASCADE', item.tablename);
    END LOOP;
    FOR item IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = current_schema() AND p.proname LIKE 'procrastinate\_%' LOOP
        EXECUTE format('DROP ROUTINE %s CASCADE', item.signature);
    END LOOP;
    FOR item IN SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = current_schema() AND t.typname LIKE 'procrastinate\_%' AND t.typtype IN ('e', 'c') LOOP
        EXECUTE format('DROP TYPE %I CASCADE', item.typname);
    END LOOP;
END;
$$;
"""


def execute_script(sql: str) -> None:
    # A DBAPI cursor without parameters: the SQL holds colons and percent signs that parameter styles would misread.
    op.get_bind().connection.cursor().execute(sql)


def upgrade() -> None:
    execute_script(SCHEMA.read_text(encoding="utf-8"))


def downgrade() -> None:
    execute_script(DROP_PROCRASTINATE)
