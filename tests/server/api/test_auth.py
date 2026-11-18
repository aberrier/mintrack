import asyncio
import datetime as dt

import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts import passwords
from mintrack.core.accounts.managers import (
    AccountManager,
    InvalidCredentialsError,
    LoginRateLimitedError,
)
from mintrack.db.database import DatabaseManager
from mintrack.db.models import LoginFailure, User, UserSession
from tests.server.api.conftest import PASSWORD, CreateUser, log_in, xsrf
from tests.server.conftest import make_client

NEW_PASSWORD = "another long passphrase here"
WRONG = {"detail": "Wrong username or password"}


async def test_login_sets_the_session_and_returns_the_user(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    user = await create_user("Alice")

    response = await log_in(api, "ALICE")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json() == {"id": str(user.id), "username": "Alice", "is_admin": False, "timezone": "UTC"}
    assert api.cookies.get("__Host-mintrack_session")
    assert api.cookies.get("XSRF-TOKEN")
    assert (await api.get("/api/auth/me")).json()["username"] == "Alice"


async def test_every_failed_login_answers_alike_and_verifies_one_hash(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_user("alice")
    await create_user("invited", password=None)
    disabled = await create_user("disabled")
    disabled.is_active = False
    verifications: list[str] = []
    verify = passwords.argon2.PasswordHasher.verify

    def counting_verify(self: passwords.argon2.PasswordHasher, password_hash: str, password: str) -> bool:
        verifications.append(password_hash)
        return verify(self, password_hash, password)

    monkeypatch.setattr(passwords.argon2.PasswordHasher, "verify", counting_verify)

    for username, password in [("alice", "wrong password!!"), ("nobody", PASSWORD), ("invited", PASSWORD)]:
        response = await log_in(api, username, password)
        assert (response.status_code, response.json()) == (fastapi.status.HTTP_401_UNAUTHORIZED, WRONG)
    response = await log_in(api, "disabled")
    assert (response.status_code, response.json()) == (fastapi.status.HTTP_401_UNAUTHORIZED, WRONG)

    assert len(verifications) == 4
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(UserSession)) == 0


async def test_five_failures_block_the_username_from_that_address_only(
    api_app: fastapi.FastAPI, create_user: CreateUser, db_session: AsyncSession
) -> None:
    await create_user("alice")
    async with make_client(api_app, peer="10.0.0.1") as attacker, make_client(api_app, peer="10.0.0.2") as owner:
        for _ in range(5):
            assert (await log_in(attacker, password="wrong password!!")).status_code == 401

        assert (await log_in(attacker)).status_code == fastapi.status.HTTP_429_TOO_MANY_REQUESTS
        assert (await log_in(owner)).status_code == fastapi.status.HTTP_200_OK

        # The window slides: once the oldest failure is 5 minutes old, one more attempt is allowed.
        oldest = await db_session.scalar(sa.select(sa.func.min(LoginFailure.failed_at)))
        assert oldest is not None
        await db_session.execute(
            sa.update(LoginFailure)
            .where(LoginFailure.failed_at == oldest)
            .values(failed_at=LoginFailure.failed_at - sa.text("interval '5 minutes'"))
        )
        assert (await log_in(attacker)).status_code == fastapi.status.HTTP_200_OK


async def test_parallel_attempts_cannot_get_past_the_limit(database: DatabaseManager) -> None:
    username = "parallel-target"

    async def attempt() -> type[Exception]:
        async with AsyncSession(database.engine) as session:
            try:
                await AccountManager(session).login(
                    username, "wrong password!!", address="10.9.9.9", now=dt.datetime.now(dt.UTC)
                )
            except (InvalidCredentialsError, LoginRateLimitedError) as error:
                await session.commit()
                return type(error)
            raise AssertionError

    try:
        results = await asyncio.gather(*(attempt() for _ in range(10)))
        assert results.count(InvalidCredentialsError) == 5
        assert results.count(LoginRateLimitedError) == 5
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(LoginFailure).where(LoginFailure.username == username))
            await cleanup.commit()


async def test_a_successful_login_clears_the_failures(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    for _ in range(4):
        await log_in(api, password="wrong password!!")

    assert (await log_in(api)).status_code == 200
    for _ in range(4):
        assert (await log_in(api, password="wrong password!!")).status_code == 401
    assert (await log_in(api)).status_code == 200


async def test_logout_ends_only_the_current_session(api_app: fastapi.FastAPI, create_user: CreateUser) -> None:
    await create_user("alice")
    async with make_client(api_app) as phone, make_client(api_app) as laptop:
        await log_in(phone)
        await log_in(laptop)

        assert (await phone.post("/api/auth/logout", headers=xsrf(phone))).status_code == 204

        assert (await phone.get("/api/auth/me")).status_code == 401
        assert (await laptop.get("/api/auth/me")).status_code == 200


async def test_logout_everywhere_ends_every_session(api_app: fastapi.FastAPI, create_user: CreateUser) -> None:
    await create_user("alice")
    async with make_client(api_app) as phone, make_client(api_app) as laptop:
        await log_in(phone)
        await log_in(laptop)

        assert (await phone.post("/api/auth/logout-all", headers=xsrf(phone))).status_code == 204

        assert (await phone.get("/api/auth/me")).status_code == 401
        assert (await laptop.get("/api/auth/me")).status_code == 401


async def test_changing_the_password_keeps_only_the_current_session(
    api_app: fastapi.FastAPI, create_user: CreateUser
) -> None:
    await create_user("alice")
    async with make_client(api_app) as phone, make_client(api_app) as laptop:
        await log_in(phone)
        await log_in(laptop)
        body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}

        wrong = await phone.post("/api/auth/password", json={**body, "current_password": "x"}, headers=xsrf(phone))
        changed = await phone.post("/api/auth/password", json=body, headers=xsrf(phone))

        assert wrong.status_code == fastapi.status.HTTP_400_BAD_REQUEST
        assert changed.status_code == fastapi.status.HTTP_204_NO_CONTENT
        assert (await phone.get("/api/auth/me")).status_code == 200
        assert (await laptop.get("/api/auth/me")).status_code == 401
        assert (await log_in(laptop, password=NEW_PASSWORD)).status_code == 200


async def test_a_new_password_needs_15_characters(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    await log_in(api)

    response = await api.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "14 characters!"}, headers=xsrf(api)
    )

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_time_zone_must_be_an_iana_name(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    user = await create_user("alice")
    await log_in(api)

    invalid = await api.patch("/api/auth/me", json={"timezone": "Mars/Olympus"}, headers=xsrf(api))
    valid = await api.patch("/api/auth/me", json={"timezone": "Europe/Paris"}, headers=xsrf(api))

    assert invalid.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert valid.json()["timezone"] == "Europe/Paris"
    assert (await db_session.get(User, user.id)) is user
    assert user.timezone == "Europe/Paris"
