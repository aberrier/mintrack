import collections.abc
import pathlib

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL
from typer.testing import CliRunner

from mintrack.cli.app import get_cli_app

USERNAME = "cli-importer"
EXPORT = pathlib.Path(__file__).parents[1] / "core" / "imports" / "data" / "yamtrack.csv"


@pytest.fixture
def engine(test_database_url: URL) -> collections.abc.Generator[sa.Engine]:
    engine = sa.create_engine(test_database_url, poolclass=sa.pool.NullPool)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, username, is_admin, is_active) VALUES (gen_random_uuid(), :name, false, true)"
            ),
            {"name": USERNAME},
        )
    yield engine
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM users WHERE username = :name"), {"name": USERNAME})
    engine.dispose()


def test_an_export_is_imported_for_a_user_and_reported(engine: sa.Engine) -> None:
    result = CliRunner().invoke(get_cli_app(), ["import", USERNAME.upper(), "yamtrack", str(EXPORT)])

    # TMDB is not configured in the tests: every row is reported, nothing is lost.
    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("Imported 0, already present 0, not matched ")
    assert "unsupported: Some Game" in result.stdout
    with engine.connect() as connection:
        status = connection.scalar(
            sa.text("SELECT status FROM import_jobs JOIN users ON users.id = user_id WHERE username = :name"),
            {"name": USERNAME},
        )
    assert status == "done"


def test_an_unknown_user_or_a_wrong_file_is_refused(engine: sa.Engine, tmp_path: pathlib.Path) -> None:
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n")

    unknown = CliRunner().invoke(get_cli_app(), ["import", "nobody", "yamtrack", str(EXPORT)])
    refused = CliRunner().invoke(get_cli_app(), ["import", USERNAME, "yamtrack", str(wrong)])

    assert (unknown.exit_code, unknown.stderr.strip()) == (1, "No user named nobody.")
    assert (refused.exit_code, refused.stderr.strip()) == (1, "This is not a Yamtrack CSV export.")
