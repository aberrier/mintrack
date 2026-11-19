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

from mintrack.__main__ import DATABASE_ERROR_EXIT_CODE
from mintrack.config import get_config
from mintrack.db.alembic import get_alembic_config, upgrade
from mintrack.worker.app import PROCRASTINATE_SCHEMA_VERSION
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


def test_a_database_upgraded_by_a_newer_version_is_named_in_one_line(
    scratch_database_url: URL, tmp_path: pathlib.Path
) -> None:
    upgrade(scratch_database_url)
    engine = sa.create_engine(scratch_database_url, poolclass=sa.pool.NullPool)
    with engine.begin() as connection:
        connection.execute(sa.text("UPDATE alembic_version SET version_num = '9999'"))
    engine.dispose()
    env = {**os.environ, "MINTRACK__DATABASE__NAME": scratch_database_url.database or ""}

    result = subprocess.run(  # noqa: S603
        [str(pathlib.Path(sys.executable).parent / "mintrack"), "db", "migrate"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == DATABASE_ERROR_EXIT_CODE
    assert result.stderr.endswith("restore a backup taken before the upgrade (README, Upgrades and rollback).\n")
    assert "Traceback" not in result.stderr


def test_the_revisions_create_what_the_models_describe(test_database_url: URL) -> None:
    # Autogenerate with the rules of env.py finds nothing to add, drop or alter: tables, columns, indexes, defaults.
    command.check(get_alembic_config(test_database_url))


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
