import collections.abc
import typing

import fastapi
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.passwords import hash_password
from mintrack.db.dependencies import get_db_session
from mintrack.db.models import User
from mintrack.integrations.tmdb.client import TMDBClient, get_tmdb_client
from tests.server.conftest import make_client

PASSWORD = "correct horse battery staple"


class CreateUser(typing.Protocol):
    async def __call__(
        self, username: str = "alice", *, password: str | None = PASSWORD, is_admin: bool = False
    ) -> User: ...


@pytest_asyncio.fixture
async def api_app(app: fastapi.FastAPI, db_session: AsyncSession, tmdb: TMDBClient) -> fastapi.FastAPI:
    """The app on the test's rolled-back session, so what requests write disappears; TMDB is the fake."""

    async def request_session() -> collections.abc.AsyncGenerator[AsyncSession]:
        # As in production, a request loses what it leaves uncommitted. Rolling back a savepoint only expires what
        # changed inside it, so the test's objects stay loaded.
        await db_session.commit()
        request_transaction = await db_session.begin_nested()
        try:
            yield db_session
        finally:
            if request_transaction.is_active:
                await request_transaction.rollback()

    app.dependency_overrides[get_db_session] = request_session
    app.dependency_overrides[get_tmdb_client] = lambda: tmdb
    return app


@pytest_asyncio.fixture
async def api(api_app: fastapi.FastAPI) -> collections.abc.AsyncGenerator[httpx.AsyncClient]:
    async with make_client(api_app) as client:
        yield client


@pytest.fixture
def create_user(db_session: AsyncSession) -> CreateUser:
    async def create(username: str = "alice", *, password: str | None = PASSWORD, is_admin: bool = False) -> User:
        user = User(
            username=username,
            password_hash=hash_password(password) if password else None,
            is_admin=is_admin,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return create


async def log_in(client: httpx.AsyncClient, username: str = "alice", password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


def xsrf(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-XSRF-TOKEN": client.cookies.get("XSRF-TOKEN") or ""}


@pytest_asyncio.fixture
async def signed_in(api: httpx.AsyncClient, create_user: CreateUser) -> httpx.AsyncClient:
    """The client of a signed-in user, sending the XSRF header on every request."""
    await create_user()
    await log_in(api)
    api.headers.update(xsrf(api))
    return api
