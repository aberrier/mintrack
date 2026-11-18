import collections.abc
import os
import pathlib
import subprocess
import sys

import procrastinate
import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import URL

from mintrack.config import get_config
from mintrack.db.alembic import get_alembic_config, upgrade
from mintrack.worker import PROCRASTINATE_SCHEMA_VERSION
from tests.conftest import drop_database, recreate_database


@pytest.fixture
def scratch_database_url() -> collections.abc.Generator[URL]:
    config = get_config().database
    name = f"test_{config.name}_migrations"
    url = recreate_database(config, name)
    yield url
    drop_database(config, name)


def test_migrate_runs_from_the_installed_package_and_is_idempotent(
    scratch_database_url: URL, tmp_path: pathlib.Path
) -> None:
    mintrack = pathlib.Path(sys.executable).parent / "mintrack"
    # No pyproject.toml or alembic.ini in the working directory.
    env = {**os.environ, "MINTRACK__DATABASE__NAME": scratch_database_url.database or ""}

    for _ in range(2):
        result = subprocess.run(  # noqa: S603
            [str(mintrack), "db", "migrate"], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    engine = sa.create_engine(scratch_database_url, poolclass=sa.pool.NullPool)
    try:
        assert sa.inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


def test_downgrading_to_base_drops_everything_the_revisions_created(scratch_database_url: URL) -> None:
    upgrade(scratch_database_url)
    command.downgrade(get_alembic_config(scratch_database_url), "base")

    engine = sa.create_engine(scratch_database_url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            leftovers = connection.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname NOT LIKE 'alembic_version%'"
                )
            )
            routines = connection.scalar(sa.text("SELECT count(*) FROM pg_proc WHERE proname LIKE 'procrastinate%'"))
    finally:
        engine.dispose()
    assert (leftovers, routines) == (0, 0)


def test_procrastinate_ships_no_migration_newer_than_the_schema_the_revisions_apply() -> None:
    # When this fails, add a revision executing the new files of procrastinate/sql/migrations in order.
    migrations = pathlib.Path(procrastinate.__file__).parent / "sql" / "migrations"
    applied = tuple(int(part) for part in PROCRASTINATE_SCHEMA_VERSION.split("."))

    newer = [
        path.name
        for path in migrations.glob("*.sql")
        if tuple(int(part) for part in path.name.split("_")[0].split(".")) > applied
    ]

    assert newer == []
