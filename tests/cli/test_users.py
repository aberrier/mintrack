import collections.abc

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL
from typer.testing import CliRunner

from mintrack.cli.app import get_cli_app

USERNAME = "cli-admin"


@pytest.fixture
def engine(test_database_url: URL) -> collections.abc.Generator[sa.Engine]:
    engine = sa.create_engine(test_database_url, poolclass=sa.pool.NullPool)
    yield engine
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM users WHERE username = :name"), {"name": USERNAME})
    engine.dispose()


def run(*args: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(get_cli_app(), list(args))
    return result.exit_code, result.stdout, result.stderr


def test_create_admin_prints_an_invitation_link(engine: sa.Engine) -> None:
    code, out, _ = run("users", "create-admin", USERNAME)

    assert code == 0
    assert out.startswith("https://mintrack.test/password#")
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT is_admin, password_hash FROM users WHERE username = :name"), {"name": USERNAME}
        ).one()
    assert row == (True, None)


def test_create_admin_refuses_a_taken_or_invalid_username(engine: sa.Engine) -> None:
    run("users", "create-admin", USERNAME)

    taken = run("users", "create-admin", USERNAME.upper())
    invalid = run("users", "create-admin", "not valid")

    assert taken[0] == 1
    assert "taken" in taken[2]
    assert invalid[0] == 1


def test_reset_link_replaces_the_link_of_an_existing_user(engine: sa.Engine) -> None:
    _, first, _ = run("users", "create-admin", USERNAME)

    code, second, _ = run("users", "reset-link", USERNAME)
    unknown = run("users", "reset-link", "nobody")

    assert code == 0
    assert second.startswith("https://mintrack.test/password#")
    assert second != first
    assert unknown[0] == 1
    assert "No user named nobody" in unknown[2]
