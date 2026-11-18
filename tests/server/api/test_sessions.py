import datetime as dt
import http.cookies

import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import get_config
from mintrack.db.dependencies import get_db_session
from mintrack.db.models import UserSession
from mintrack.server.api.asgi import build_app
from tests.server.api.conftest import CreateUser, log_in
from tests.server.conftest import make_client

FOURTEEN_DAYS = str(14 * 24 * 3600)


def parse_set_cookies(response: httpx.Response) -> dict[str, http.cookies.Morsel[str]]:
    cookies: dict[str, http.cookies.Morsel[str]] = {}
    for header in response.headers.get_list("set-cookie"):
        jar = http.cookies.SimpleCookie()
        jar.load(header)
        cookies.update(jar)
    return cookies


@pytest.mark.parametrize(
    ("public_url", "cookie_name"),
    [("https://mintrack.test", "__Host-mintrack_session"), ("http://mintrack.test", "mintrack_session")],
)
async def test_the_session_cookie_follows_the_public_url(
    public_url: str,
    cookie_name: str,
    create_user: CreateUser,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_user("alice")
    monkeypatch.setenv("MINTRACK__PROJECT__PUBLIC_URL", public_url)
    get_config.cache_clear()
    try:
        app = build_app(get_config())
        app.dependency_overrides[get_db_session] = lambda: db_session
        async with make_client(app) as client:
            cookies = parse_set_cookies(await log_in(client))
    finally:
        monkeypatch.undo()
        get_config.cache_clear()
    session = cookies[cookie_name]
    assert session["httponly"] is True
    assert bool(session["secure"]) is public_url.startswith("https")
    assert (session["samesite"], session["path"], session["max-age"]) == ("strict", "/", FOURTEEN_DAYS)
    xsrf = cookies["XSRF-TOKEN"]
    assert not xsrf["httponly"]
    assert (xsrf["samesite"], xsrf["max-age"]) == ("strict", FOURTEEN_DAYS)
    stored = await db_session.scalar(sa.select(UserSession.token_hash))
    assert stored is not None
    assert len(stored) == 32
    assert stored != session.value.encode()


async def test_a_session_unused_for_14_days_is_refused(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    await create_user("alice")
    await log_in(api)
    await db_session.execute(
        sa.update(UserSession).values(last_used_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=14, minutes=1))
    )

    assert (await api.get("/api/auth/me")).status_code == fastapi.status.HTTP_401_UNAUTHORIZED


async def test_using_a_session_after_an_hour_renews_it(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    await create_user("alice")
    await log_in(api)
    unrenewed = await api.get("/api/auth/me")
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=13)
    await db_session.execute(sa.update(UserSession).values(last_used_at=old))

    renewed = await api.get("/api/auth/me")

    assert "__Host-mintrack_session" not in parse_set_cookies(unrenewed)
    assert parse_set_cookies(renewed)["__Host-mintrack_session"]["max-age"] == FOURTEEN_DAYS
    last_used_at = await db_session.scalar(sa.select(UserSession.last_used_at))
    assert last_used_at is not None
    assert last_used_at > old


async def test_a_disabled_users_session_is_refused(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    user = await create_user("alice")
    await log_in(api)

    user.is_active = False

    assert (await api.get("/api/auth/me")).status_code == fastapi.status.HTTP_401_UNAUTHORIZED
