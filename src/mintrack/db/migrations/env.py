import typing

import sqlalchemy as sa
from alembic import context
from alembic.operations.ops import MigrationScript
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from mintrack.db.config import CONNECT_ARGS
from mintrack.db.models import DatabaseModel


def process_revision_directives(
    _context: MigrationContext,
    _revision: tuple[str, str],
    directives: list[MigrationScript],
) -> None:
    """Number revisions sequentially (0001, 0002...) instead of random hashes."""
    head_revision = ScriptDirectory.from_config(context.config).get_current_head()
    last_revision = int(head_revision) if head_revision is not None else 0
    directives[0].rev_id = f"{last_revision + 1:04}"


def migrate() -> None:
    options: dict[str, typing.Any] = {
        "target_metadata": DatabaseModel.metadata,
        "process_revision_directives": process_revision_directives,
        "compare_server_default": True,
    }
    url = context.config.attributes["url"]

    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **options)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = sa.create_engine(url, poolclass=sa.pool.NullPool, connect_args=CONNECT_ARGS, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


migrate()
