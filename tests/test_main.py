import pytest

from mintrack.__main__ import CONFIG_ERROR_EXIT_CODE, DATABASE_ERROR_EXIT_CODE, main
from tests.conftest import DATABASE_PASSWORD


def test_the_cli_reports_config_errors_without_traceback(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.delenv("MINTRACK__DATABASE__PASSWORD")
    env.setenv("MINTRACK__DATABASE__PORT", "port-5432")
    env.setattr("sys.argv", ["mintrack", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    stderr = capsys.readouterr().err
    assert exit_info.value.code == CONFIG_ERROR_EXIT_CODE
    assert "MINTRACK__DATABASE__PASSWORD: Field required" in stderr
    assert "MINTRACK__DATABASE__PORT: Input should be a valid integer" in stderr
    assert "port-5432" not in stderr
    assert "Traceback" not in stderr


def test_the_cli_reports_an_unreachable_database_without_traceback(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.setenv("MINTRACK__DATABASE__HOST", "127.0.0.1")
    env.setenv("MINTRACK__DATABASE__PORT", "1")
    env.setattr("sys.argv", ["mintrack", "db", "migrate"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    stderr = capsys.readouterr().err
    assert exit_info.value.code == DATABASE_ERROR_EXIT_CODE
    assert stderr.startswith("MinTrack cannot reach PostgreSQL at 127.0.0.1:1: ")
    assert DATABASE_PASSWORD not in stderr
    assert "Traceback" not in stderr
