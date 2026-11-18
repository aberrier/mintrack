import datetime as dt

import fastapi
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.managers import AccountManager
from mintrack.db.models import User
from tests.server.api.conftest import PASSWORD, CreateUser, log_in

NEW_PASSWORD = "a brand new passphrase"
INVALID = {"detail": "This link is invalid or has expired."}


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def use(client: httpx.AsyncClient, token: str, timezone: str | None = "Europe/Paris") -> httpx.Response:
    return await client.post(
        "/api/auth/password-link/use", json={"token": token, "password": NEW_PASSWORD, "timezone": timezone}
    )


async def test_an_invitation_sets_the_password_and_time_zone_and_logs_in(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user("alice", password=None)
    token = AccountManager.issue_link(user, now=now())

    described = await api.post("/api/auth/password-link", json={"token": token})
    used = await use(api, token)

    assert described.json() == {"username": "alice"}
    assert used.status_code == fastapi.status.HTTP_200_OK
    assert used.json()["timezone"] == "Europe/Paris"
    assert (await api.get("/api/auth/me")).status_code == 200
    assert (await use(api, token)).json() == INVALID
    assert (await log_in(api, password=NEW_PASSWORD)).status_code == 200


async def test_a_reset_keeps_the_time_zone_and_ends_every_session(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    user = await create_user("alice")
    user.timezone = "Asia/Tokyo"
    other_session = await AccountManager(db_session).create_session(user, now=now())
    token = AccountManager.issue_link(user, now=now())

    described = await api.post("/api/auth/password-link", json={"token": token})
    used = await use(api, token)

    assert described.json() == {"username": "alice"}
    assert used.json()["timezone"] == "Asia/Tokyo"
    assert await AccountManager(db_session).get_session(other_session, now=now()) is None
    assert (await log_in(api, password=PASSWORD)).status_code == 401


async def test_a_link_lasts_7_days_for_an_invitation_and_24_hours_for_a_reset(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    invited = await create_user("invited", password=None)
    active = await create_user("active")
    invitation = AccountManager.issue_link(invited, now=now() - dt.timedelta(days=7, minutes=1))
    reset = AccountManager.issue_link(active, now=now() - dt.timedelta(hours=24, minutes=1))
    fresh_invitation = AccountManager.issue_link(
        await create_user("fresh", password=None), now=now() - dt.timedelta(days=6)
    )

    for token in (invitation, reset):
        response = await api.post("/api/auth/password-link", json={"token": token})
        assert (response.status_code, response.json()) == (fastapi.status.HTTP_400_BAD_REQUEST, INVALID)
        assert (await use(api, token)).json() == INVALID
    assert (await api.post("/api/auth/password-link", json={"token": fresh_invitation})).status_code == 200


async def test_a_replaced_unknown_or_disabled_users_link_is_refused(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user("alice", password=None)
    replaced = AccountManager.issue_link(alice, now=now())
    AccountManager.issue_link(alice, now=now())
    bob = await create_user("bob", password=None)
    disabled = AccountManager.issue_link(bob, now=now())
    bob.is_active = False

    for token in (replaced, disabled, "unknown"):
        assert (await use(api, token)).json() == INVALID


async def test_the_password_needs_15_to_128_characters(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    token = AccountManager.issue_link(await create_user("alice", password=None), now=now())

    for password in ("x" * 14, "x" * 129):
        response = await api.post("/api/auth/password-link/use", json={"token": token, "password": password})
        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_link_works_once(create_user: CreateUser, db_session: AsyncSession) -> None:
    user = await create_user("alice", password=None)
    token = AccountManager.issue_link(user, now=now())
    manager = AccountManager(db_session)

    first = await manager.use_link(token, NEW_PASSWORD, timezone=None, now=now())
    second = await manager.use_link(token, NEW_PASSWORD, timezone=None, now=now())

    assert isinstance(first, User)
    assert second is None
