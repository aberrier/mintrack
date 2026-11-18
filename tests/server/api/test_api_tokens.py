import datetime as dt
import hashlib
import re

import fastapi
import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.api_tokens.managers import ApiTokenManager
from mintrack.db.models import ApiToken, User

TOKEN = re.compile(r"^mt_[A-Za-z0-9_-]{43}$")


@pytest_asyncio.fixture
async def user(signed_in: httpx.AsyncClient, db_session: AsyncSession) -> User:
    """The signed-in user."""
    return (await db_session.scalars(sa.select(User).where(User.username == "alice"))).one()


async def other_user_token(db_session: AsyncSession) -> ApiToken:
    other = User(username="someone-else")
    db_session.add(other)
    await db_session.flush()
    token, _ = await ApiTokenManager(db_session).create(other, "theirs", dt.datetime.now(dt.UTC))
    return token


async def test_create_returns_the_token_once_and_stores_only_its_hash(
    signed_in: httpx.AsyncClient, db_session: AsyncSession, user: User
) -> None:
    response = await signed_in.post("/api/api-tokens", json={"name": "  Claude  "})

    assert response.status_code == fastapi.status.HTTP_201_CREATED
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert TOKEN.match(body["token"])
    assert body["name"] == "Claude"
    assert body["last_used_at"] is None
    stored = (await db_session.scalars(sa.select(ApiToken).where(ApiToken.user_id == user.id))).one()
    assert stored.token_hash == hashlib.sha256(body["token"].encode()).digest()


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_create_refuses_a_blank_or_long_name(signed_in: httpx.AsyncClient, name: str) -> None:
    response = await signed_in.post("/api/api-tokens", json={"name": name})

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_list_shows_the_users_tokens_newest_first_without_their_value(
    signed_in: httpx.AsyncClient, db_session: AsyncSession, user: User
) -> None:
    manager = ApiTokenManager(db_session)
    now = dt.datetime.now(dt.UTC)
    await manager.create(user, "old", now - dt.timedelta(days=1))
    await manager.create(user, "new", now)
    await other_user_token(db_session)

    response = await signed_in.get("/api/api-tokens")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert [token["name"] for token in response.json()] == ["new", "old"]
    assert all(set(token) == {"id", "name", "created_at", "last_used_at"} for token in response.json())


async def test_revoke_deletes_the_users_token(
    signed_in: httpx.AsyncClient, db_session: AsyncSession, user: User
) -> None:
    token, _ = await ApiTokenManager(db_session).create(user, "Claude", dt.datetime.now(dt.UTC))

    response = await signed_in.delete(f"/api/api-tokens/{token.id}")

    assert response.status_code == fastapi.status.HTTP_204_NO_CONTENT
    assert await db_session.get(ApiToken, token.id) is None


async def test_revoke_answers_404_for_another_users_token(
    signed_in: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    token = await other_user_token(db_session)

    response = await signed_in.delete(f"/api/api-tokens/{token.id}")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert await db_session.get(ApiToken, token.id) is not None


async def test_a_name_with_a_nul_character_is_refused(signed_in: httpx.AsyncClient) -> None:
    response = await signed_in.post("/api/api-tokens", json={"name": "bad\u0000name"})

    assert response.status_code == 422
