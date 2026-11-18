import asyncio
import collections.abc
import contextlib
import dataclasses
import datetime as dt
import uuid

import fastapi
import httpx2
import pytest
import pytest_asyncio
import sqlalchemy as sa
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import get_config
from mintrack.core.api_tokens.managers import ApiTokenManager
from mintrack.db.database import DatabaseManager
from mintrack.db.models import Media, User
from mintrack.integrations.tmdb.client import TMDBClient
from mintrack.server.api.asgi import build_app
from mintrack.server.mcp import tools
from tests.server.conftest import BASE_URL


@dataclasses.dataclass
class TokenUser:
    user: User
    token: str


@pytest_asyncio.fixture
async def mcp_app(database: DatabaseManager) -> collections.abc.AsyncGenerator[fastapi.FastAPI]:
    """The app with its lifespan running, as the MCP server needs, without the background worker.

    The lifespan runs in its own task: the fixture's setup and teardown may run in different tasks, and the MCP
    session manager's task group must be exited in the task that entered it.
    """
    config = get_config()
    app = build_app(config.model_copy(update={"server": config.server.model_copy(update={"run_worker": False})}))
    started, stop = asyncio.Event(), asyncio.Event()

    async def run() -> None:
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    task = asyncio.create_task(run())
    await started.wait()
    yield app
    stop.set()
    await task


@pytest_asyncio.fixture(autouse=True)
async def tools_tmdb(
    monkeypatch: pytest.MonkeyPatch, tmdb: TMDBClient, database: DatabaseManager
) -> collections.abc.AsyncGenerator[None]:
    """The tools ask the fake TMDB; the media they cache are deleted afterwards, as the tools commit them."""
    monkeypatch.setattr(tools, "get_tmdb_client", lambda: tmdb)
    started = dt.datetime.now(dt.UTC)
    yield
    async with AsyncSession(database.engine) as session:
        await session.execute(sa.delete(Media).where(Media.refreshed_at >= started))
        await session.commit()


@contextlib.asynccontextmanager
async def committed_token_user(database: DatabaseManager) -> collections.abc.AsyncGenerator[TokenUser]:
    """A committed user with an API token: MCP requests run in their own sessions, outside the test's transaction."""
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        user = User(username=f"mcp-{uuid.uuid4().hex[:8]}", timezone="Europe/Paris")
        session.add(user)
        await session.flush()
        _, token = await ApiTokenManager(session).create(user, "test", dt.datetime.now(dt.UTC))
        await session.commit()
    yield TokenUser(user, token)
    async with AsyncSession(database.engine) as session:
        await session.delete(await session.get(User, user.id))
        await session.commit()


@pytest_asyncio.fixture
async def token_user(database: DatabaseManager) -> collections.abc.AsyncGenerator[TokenUser]:
    async with committed_token_user(database) as token_user:
        yield token_user


@pytest_asyncio.fixture
async def other_token_user(database: DatabaseManager) -> collections.abc.AsyncGenerator[TokenUser]:
    async with committed_token_user(database) as token_user:
        yield token_user


@contextlib.asynccontextmanager
async def mcp_client(app: fastapi.FastAPI, token: str) -> collections.abc.AsyncGenerator[Client]:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={"Authorization": f"Bearer {token}"})
    async with http, Client(streamable_http_client(f"{BASE_URL}/mcp", http_client=http), cache=None) as client:
        yield client
