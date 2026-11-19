import asyncio
import datetime as dt
import pathlib

import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import ServerConfig, get_config
from mintrack.core.accounts.managers import AccountManager, LinkProblem, UserGoneError
from mintrack.db.database import DatabaseManager
from mintrack.db.models import User
from mintrack.server.api.asgi import build_app
from tests.server.api.conftest import PASSWORD, CreateUser, log_in

NEW_PASSWORD = "a brand new passphrase"
INDEX = "<!doctype html><title>MinTrack</title>"
# User agents of link previews (messaging apps, mail scanners), which fetch a link before the person opens it.
PREVIEW_AGENTS = [
    "WhatsApp/2.24.1 A",
    "facebookexternalhit/1.1",
    "TelegramBot (like TwitterBot)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Microsoft Office/16.0",
]


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def refused(problem: LinkProblem) -> tuple[int, str]:
    return fastapi.status.HTTP_400_BAD_REQUEST, problem


@pytest.fixture
def app(tmp_path: pathlib.Path) -> fastapi.FastAPI:
    """The app serving a built frontend, so the link's page answers like in production."""
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    config = get_config()
    return build_app(config.model_copy(update={"server": ServerConfig(frontend_dist=tmp_path)}))


@pytest.fixture
def manager(db_session: AsyncSession) -> AccountManager:
    return AccountManager(db_session)


async def describe(client: httpx.AsyncClient, token: str) -> tuple[int, str]:
    response = await client.post("/api/auth/password-link", json={"token": token})
    body = response.json()
    return response.status_code, body.get("reason") or body.get("username")


async def use(client: httpx.AsyncClient, token: str, timezone: str | None = "Europe/Paris") -> httpx.Response:
    return await client.post(
        "/api/auth/password-link/use", json={"token": token, "password": NEW_PASSWORD, "timezone": timezone}
    )


async def use_answer(client: httpx.AsyncClient, token: str) -> tuple[int, str]:
    response = await use(client, token)
    body = response.json()
    return response.status_code, body.get("reason") or body.get("username")


async def test_an_invitation_sets_the_password_and_time_zone_and_logs_in(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    user = await create_user("alice", password=None)
    token = await manager.issue_link(user, now=now())

    described = await api.post("/api/auth/password-link", json={"token": token})
    used = await use(api, token)

    assert described.json() == {"username": "alice"}
    assert used.status_code == fastapi.status.HTTP_200_OK
    assert used.json()["timezone"] == "Europe/Paris"
    assert (await api.get("/api/auth/me")).status_code == 200
    assert (await log_in(api, password=NEW_PASSWORD)).status_code == 200


async def test_previews_and_repeated_visits_leave_the_link_usable(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    token = await manager.issue_link(await create_user("alice", password=None), now=now())

    for agent in PREVIEW_AGENTS:
        for method in ("GET", "HEAD"):
            # Previews never get the fragment that holds the token; some scanners send it escaped in the path.
            for path in ("/password", f"/password%23{token}"):
                response = await api.request(method, path, headers={"user-agent": agent})
                assert response.status_code == fastapi.status.HTTP_200_OK
    for _ in range(3):
        assert await describe(api, token) == (200, "alice")

    assert (await use(api, token)).status_code == fastapi.status.HTTP_200_OK


async def test_a_reset_keeps_the_time_zone_and_ends_every_session(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    user = await create_user("alice")
    user.timezone = "Asia/Tokyo"
    other_session = await manager.create_session(user, now=now())
    token = await manager.issue_link(user, now=now())

    described = await api.post("/api/auth/password-link", json={"token": token})
    used = await use(api, token)

    assert described.json() == {"username": "alice"}
    assert used.json()["timezone"] == "Asia/Tokyo"
    assert await manager.get_session(other_session, now=now()) is None
    assert (await log_in(api, password=PASSWORD)).status_code == 401


async def test_a_link_lasts_7_days_for_an_invitation_and_24_hours_for_a_reset(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    invitation = await manager.issue_link(
        await create_user("invited", password=None), now=now() - dt.timedelta(days=7, minutes=1)
    )
    reset = await manager.issue_link(await create_user("active"), now=now() - dt.timedelta(hours=24, minutes=1))
    fresh_invitation = await manager.issue_link(
        await create_user("fresh", password=None), now=now() - dt.timedelta(days=6, hours=23)
    )

    for token in (invitation, reset):
        assert await describe(api, token) == refused(LinkProblem.EXPIRED)
        assert await use_answer(api, token) == refused(LinkProblem.EXPIRED)
    assert await describe(api, fresh_invitation) == (200, "fresh")


async def test_each_refused_link_says_why(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    alice = await create_user("alice", password=None)
    replaced = await manager.issue_link(alice, now=now())
    used = await manager.issue_link(alice, now=now())
    bob = await create_user("bob", password=None)
    disabled = await manager.issue_link(bob, now=now())
    await manager.set_active(bob, active=False)
    # Disabling a user did not clear their link before 0.3.
    carol = await create_user("carol", password=None)
    disabled_with_link = await manager.issue_link(carol, now=now())
    carol.is_active = False
    assert (await use(api, used)).status_code == fastapi.status.HTTP_200_OK

    response = await api.post("/api/auth/password-link", json={"token": replaced})
    assert response.json() == {
        "detail": "A newer link replaced this one. Open the latest link, or ask your admin for a new one.",
        "reason": "replaced",
    }
    assert await describe(api, used) == refused(LinkProblem.USED)
    assert await use_answer(api, used) == refused(LinkProblem.USED)
    for token in (disabled, disabled_with_link, "unknown", ""):
        assert await describe(api, token) == refused(LinkProblem.INVALID)
        assert await use_answer(api, token) == refused(LinkProblem.INVALID)


async def test_the_password_needs_15_to_128_characters(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    token = await manager.issue_link(await create_user("alice", password=None), now=now())

    for password in ("x" * 14, "x" * 129):
        response = await api.post("/api/auth/password-link/use", json={"token": token, "password": password})
        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await describe(api, token) == (200, "alice")


async def test_a_link_works_once(create_user: CreateUser, manager: AccountManager) -> None:
    user = await create_user("alice", password=None)
    token = await manager.issue_link(user, now=now())

    first = await manager.use_link(token, NEW_PASSWORD, timezone=None, now=now())
    second = await manager.use_link(token, NEW_PASSWORD, timezone=None, now=now())

    assert isinstance(first, User)
    assert second == LinkProblem.USED


async def test_a_spent_link_says_why_for_30_days(
    api: httpx.AsyncClient, create_user: CreateUser, manager: AccountManager
) -> None:
    alice = await create_user("alice", password=None)
    old = await manager.issue_link(alice, now=now() - dt.timedelta(days=40))
    recent = await manager.issue_link(alice, now=now() - dt.timedelta(days=31))
    await manager.issue_link(alice, now=now() - dt.timedelta(days=1))

    await manager.delete_expired_sessions(now())

    assert await describe(api, old) == refused(LinkProblem.INVALID)
    assert await describe(api, recent) == refused(LinkProblem.REPLACED)


async def test_concurrent_uses_of_a_link_set_the_password_once(database: DatabaseManager) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as setup:
        user, token = await AccountManager(setup).create_user("race-link", is_admin=False, now=now())
        await setup.commit()

    async def use_once() -> str:
        async with AsyncSession(database.engine) as session:
            result = await AccountManager(session).use_link(token, NEW_PASSWORD, timezone=None, now=now())
            await asyncio.sleep(0.05)
            await session.commit()
            return "set" if isinstance(result, User) else result

    try:
        assert sorted(await asyncio.gather(use_once(), use_once())) == ["set", LinkProblem.USED]
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(User).where(User.id == user.id))
            await cleanup.commit()


async def test_a_link_issued_while_an_invitation_is_used_lasts_24_hours(database: DatabaseManager) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as setup:
        user, token = await AccountManager(setup).create_user("race-lifetime", is_admin=False, now=now())
        await setup.commit()

    async with AsyncSession(database.engine) as using, AsyncSession(database.engine) as issuing:
        # Loaded before the invitation is used, so it still has no password.
        fetched = await issuing.get(User, user.id)
        assert fetched is not None
        assert fetched.password_hash is None
        assert isinstance(await AccountManager(using).use_link(token, NEW_PASSWORD, timezone=None, now=now()), User)

        async def commit_use() -> None:
            await asyncio.sleep(0.05)
            await using.commit()

        issued_at = now()
        await asyncio.gather(commit_use(), AccountManager(issuing).issue_link(fetched, now=issued_at))
        expires_at = fetched.link_expires_at
        await issuing.commit()

    try:
        assert expires_at == issued_at + dt.timedelta(hours=24)
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(User).where(User.id == user.id))
            await cleanup.commit()


async def test_no_link_is_issued_for_a_user_deleted_since_it_was_loaded(database: DatabaseManager) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as setup:
        user, _ = await AccountManager(setup).create_user("race-delete", is_admin=False, now=now())
        await setup.commit()

    async with AsyncSession(database.engine) as issuing:
        fetched = await issuing.get(User, user.id)
        assert fetched is not None
        async with AsyncSession(database.engine) as deleting:
            await deleting.execute(sa.delete(User).where(User.id == user.id))
            await deleting.commit()

        with pytest.raises(UserGoneError):
            await AccountManager(issuing).issue_link(fetched, now=now())


async def test_a_link_replaced_while_it_is_used_fails_neither_request(database: DatabaseManager) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as setup:
        user, token = await AccountManager(setup).create_user("race-replace", is_admin=False, now=now())
        await setup.commit()

    async def use_once() -> None:
        async with AsyncSession(database.engine) as session:
            await AccountManager(session).use_link(token, NEW_PASSWORD, timezone=None, now=now())
            await asyncio.sleep(0.05)
            await session.commit()

    async def replace() -> None:
        async with AsyncSession(database.engine) as session:
            fetched = await session.get(User, user.id)
            assert fetched is not None
            await AccountManager(session).issue_link(fetched, now=now())
            await asyncio.sleep(0.05)
            await session.commit()

    try:
        await asyncio.gather(use_once(), replace(), replace())
        async with AsyncSession(database.engine) as session:
            spent = await AccountManager(session).check_link(token, now=now())
        assert spent in {LinkProblem.USED, LinkProblem.REPLACED}
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(User).where(User.id == user.id))
            await cleanup.commit()
