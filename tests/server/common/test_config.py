import time

import fastapi
import pytest

from mintrack.config import get_config
from mintrack.db.database import DatabaseManager
from mintrack.server.api.asgi import build_app
from mintrack.server.common import config as server_config
from tests.worker.recording import RecordingWorkerApp


async def test_the_server_runs_the_worker_and_stops_it_promptly(database: DatabaseManager) -> None:
    app: fastapi.FastAPI = build_app(get_config())

    async with app.router.lifespan_context(app):
        started = time.monotonic()

    assert time.monotonic() - started < 6


async def test_without_run_worker_the_server_leaves_the_jobs_to_the_worker_service(
    database: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker_app = RecordingWorkerApp()
    monkeypatch.setattr(server_config, "get_worker_app", lambda: worker_app)
    config = get_config()
    app = build_app(config.model_copy(update={"server": config.server.model_copy(update={"run_worker": False})}))

    async with app.router.lifespan_context(app):
        pass

    assert worker_app.runs == []
