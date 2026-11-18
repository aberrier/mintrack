import pytest
from typer.testing import CliRunner

from mintrack.cli.app import get_cli_app
from mintrack.cli.commands import worker
from tests.worker.recording import RecordingWorkerApp


def test_the_worker_command_runs_the_worker_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_app = RecordingWorkerApp()
    monkeypatch.setattr(worker, "get_worker_app", lambda: worker_app)

    result = CliRunner().invoke(get_cli_app(), ["worker"])

    assert result.exit_code == 0
    assert worker_app.runs == ["run_worker"]
