import asyncio
import datetime as dt

import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import get_config
from mintrack.core.accounts.managers import AccountManager, SetupClosedError
from mintrack.db.database import DatabaseManager
from mintrack.db.models import LoginFailure, User
from tests.server.api.conftest import PASSWORD, CreateUser

SETUP = {"username": "Admin", "password": PASSWORD}


async def setup_open(api: httpx.AsyncClient) -> bool:
    return (await api.get("/api/auth/setup")).json()["open"]


async def test_the_first_admin_is_created_signed_in_and_only_once(api: httpx.AsyncClient) -> None:
    assert await setup_open(api)

    response = await api.post("/api/auth/setup", json={**SETUP, "timezone": "Europe/Paris"})

    assert response.status_code == fastapi.status.HTTP_201_CREATED
    me = (await api.get("/api/auth/me")).json()
    assert (me["username"], me["is_admin"], me["timezone"]) == ("Admin", True, "Europe/Paris")
    assert not await setup_open(api)
    again = await api.post("/api/auth/setup", json={**SETUP, "username": "other"})
    assert again.status_code == fastapi.status.HTTP_409_CONFLICT


async def test_setup_is_closed_once_any_user_exists(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice", password=None)

    assert not await setup_open(api)
    assert (await api.post("/api/auth/setup", json=SETUP)).status_code == fastapi.status.HTTP_409_CONFLICT


async def test_setup_turned_off_is_never_offered(
    api: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_config().accounts, "setup", False)

    assert not await setup_open(api)
    assert (await api.post("/api/auth/setup", json=SETUP)).status_code == fastapi.status.HTTP_409_CONFLICT
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    "body",
    [
        {**SETUP, "password": "too short"},
        {**SETUP, "password": "x" * 1025},
        {**SETUP, "username": "with space"},
        {**SETUP, "timezone": "Mars/Olympus"},
    ],
)
async def test_the_admin_account_follows_the_usual_rules(api: httpx.AsyncClient, body: dict[str, str]) -> None:
    response = await api.post("/api/auth/setup", json=body)

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await setup_open(api)


async def test_refused_setups_are_limited_like_logins(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    statuses = [(await api.post("/api/auth/setup", json=SETUP)).status_code for _ in range(6)]

    assert statuses == [fastapi.status.HTTP_409_CONFLICT] * 5 + [fastapi.status.HTTP_429_TOO_MANY_REQUESTS]


async def test_simultaneous_setups_create_one_admin(database: DatabaseManager) -> None:
    address = "10.8.8.8"

    async def attempt(username: str) -> bool:
        async with AsyncSession(database.engine) as session:
            try:
                await AccountManager(session).create_first_admin(
                    username, PASSWORD, address=address, now=dt.datetime.now(dt.UTC)
                )
            except SetupClosedError:
                await session.commit()
                return False
            await session.commit()
            return True

    try:
        created = await asyncio.gather(*(attempt(f"admin{index}") for index in range(4)))
        async with AsyncSession(database.engine) as session:
            admins = await session.scalar(sa.select(sa.func.count()).select_from(User).where(User.is_admin))
        assert (created.count(True), admins) == (1, 1)
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(User))
            await cleanup.execute(sa.delete(LoginFailure).where(LoginFailure.address == address))
            await cleanup.commit()
