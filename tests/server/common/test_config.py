import time

import fastapi

from mintrack.config import get_config
from mintrack.db.database import DatabaseManager
from mintrack.server.api.asgi import build_app


async def test_the_server_runs_the_worker_and_stops_it_promptly(database: DatabaseManager) -> None:
    app: fastapi.FastAPI = build_app(get_config())

    async with app.router.lifespan_context(app):
        started = time.monotonic()

    assert time.monotonic() - started < 6
