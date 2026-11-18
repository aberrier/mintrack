import collections.abc
import contextlib
import typing

import fastapi

from mintrack.config import Config, Environment
from mintrack.db.database import get_database

API_PREFIX = "/api"


@contextlib.asynccontextmanager
async def lifespan(_: fastapi.FastAPI) -> collections.abc.AsyncGenerator[None]:
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
        "lifespan": lifespan,
    }
