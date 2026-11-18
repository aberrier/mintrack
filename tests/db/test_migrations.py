import collections.abc
import os
import pathlib
import subprocess
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL

from mintrack.config import get_config
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
