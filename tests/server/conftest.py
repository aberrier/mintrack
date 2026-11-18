import collections.abc

import fastapi
import httpx
import pytest_asyncio

from mintrack.config import get_config
from mintrack.server.api.asgi import build_app

# The test public_url. httpx only sends HTTPS-only cookies to an https origin.
BASE_URL = "https://mintrack.test"


def make_client(app: fastapi.FastAPI, *, peer: str = "127.0.0.1") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(peer, 50000), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url=BASE_URL)


@pytest_asyncio.fixture
async def app() -> fastapi.FastAPI:
    return build_app(get_config())


@pytest_asyncio.fixture
async def client(app: fastapi.FastAPI) -> collections.abc.AsyncGenerator[httpx.AsyncClient]:
    async with make_client(app) as client:
        yield client
