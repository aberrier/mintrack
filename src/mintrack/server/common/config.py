import asyncio
import collections.abc
import contextlib
import functools
import typing

import fastapi

from mintrack.config import Config, Environment
from mintrack.db.database import get_database
from mintrack.worker import get_worker_app

API_PREFIX = "/api"


@contextlib.asynccontextmanager
async def lifespan(_: fastapi.FastAPI, *, run_worker: bool) -> collections.abc.AsyncGenerator[None]:
    worker_app = get_worker_app()
    if run_worker:
        async with worker_app.open_async():
            # uvicorn keeps its signal handlers; cancelling lets running jobs finish within the graceful timeout.
            worker = asyncio.create_task(worker_app.run_worker_async(install_signal_handlers=False))
            yield
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
    else:
        yield
    await get_database().close()


def get_fastapi_common_config(config: Config) -> dict[str, typing.Any]:
    # No CORS middleware: the API is only called by the app it serves, from the same origin.
    docs_enabled = config.project.environment is not Environment.PROD
    return {
        "title": "MinTrack",
        "version": config.project.version,
        "redirect_slashes": False,
        "docs_url": f"{API_PREFIX}/docs" if docs_enabled else None,
        "openapi_url": f"{API_PREFIX}/openapi.json" if docs_enabled else None,
        "redoc_url": None,
        "lifespan": functools.partial(lifespan, run_worker=config.server.run_worker),
    }
