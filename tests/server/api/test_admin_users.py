import asyncio
import datetime as dt

import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.managers import AccountManager, LastAdminError
from mintrack.db.database import DatabaseManager
from mintrack.db.models import User
from tests.server.api.conftest import CreateUser, log_in, xsrf
from tests.server.conftest import make_client

LINK_PREFIX = "https://mintrack.test/password#"


@pytest.fixture
async def admin(api: httpx.AsyncClient, create_user: CreateUser) -> httpx.AsyncClient:
    await create_user("root", is_admin=True)
    await log_in(api, "root")
    return api


def token_of(link: str) -> str:
    assert link.startswith(LINK_PREFIX)
    return link.removeprefix(LINK_PREFIX)


async def test_an_admin_invites_a_user_who_then_sets_a_password(
    admin: httpx.AsyncClient, api_app: fastapi.FastAPI
) -> None:
    created = await admin.post("/api/admin/users", json={"username": "Alice"}, headers=xsrf(admin))
    taken = await admin.post("/api/admin/users", json={"username": "alice"}, headers=xsrf(admin))
    invalid = await admin.post("/api/admin/users", json={"username": "al ice"}, headers=xsrf(admin))

    assert created.status_code == fastapi.status.HTTP_201_CREATED
    assert created.json()["user"]["status"] == "invited"
    expires_at = dt.datetime.fromisoformat(created.json()["expires_at"])
    assert dt.timedelta(days=6, hours=23) < expires_at - dt.datetime.now(dt.UTC) <= dt.timedelta(days=7)
    assert created.json()["user"]["link_expires_at"] == created.json()["expires_at"]
    assert taken.status_code == fastapi.status.HTTP_409_CONFLICT
    assert invalid.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    async with make_client(api_app) as invitee:
        token = token_of(created.json()["link"])
        used = await invitee.post(
            "/api/auth/password-link/use", json={"token": token, "password": "a long enough passphrase"}
        )
        assert used.status_code == 200
    users = {user["username"]: user for user in (await admin.get("/api/admin/users")).json()}
    assert users["Alice"]["status"] == "active"
    assert users["Alice"]["last_seen_at"] is not None
    assert users["root"]["is_admin"] is True


async def test_a_new_link_replaces_the_previous_one(
    admin: httpx.AsyncClient, api_app: fastapi.FastAPI, create_user: CreateUser
) -> None:
    user = await create_user("alice")
    first = (await admin.post(f"/api/admin/users/{user.id}/link", headers=xsrf(admin))).json()["link"]
    second = (await admin.post(f"/api/admin/users/{user.id}/link", headers=xsrf(admin))).json()["link"]

    async with make_client(api_app) as invitee:
        for link, status in [(first, 400), (second, 200)]:
            response = await invitee.post("/api/auth/password-link", json={"token": token_of(link)})
            assert response.status_code == status


async def test_a_disabled_user_gets_no_new_link(
    admin: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    user = await create_user("alice")
    user.is_active = False

    response = await admin.post(f"/api/admin/users/{user.id}/link", headers=xsrf(admin))

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert user.link_token_hash is None


async def test_disabling_a_user_ends_their_sessions_and_link(
    admin: httpx.AsyncClient, api_app: fastapi.FastAPI, create_user: CreateUser
) -> None:
    user = await create_user("alice")
    link = (await admin.post(f"/api/admin/users/{user.id}/link", headers=xsrf(admin))).json()["link"]
    async with make_client(api_app) as invitee:
        await log_in(invitee)

        disabled = await admin.patch(f"/api/admin/users/{user.id}", json={"is_active": False}, headers=xsrf(admin))

        assert disabled.json()["status"] == "disabled"
        # The sessions are gone, not when the user was last seen.
        assert disabled.json()["last_seen_at"] is not None
        assert (await invitee.get("/api/auth/me")).status_code == 401
        assert (await log_in(invitee)).status_code == 401
        assert (await invitee.post("/api/auth/password-link", json={"token": token_of(link)})).status_code == 400

        await admin.patch(f"/api/admin/users/{user.id}", json={"is_active": True}, headers=xsrf(admin))
        assert (await log_in(invitee)).status_code == 200


async def test_an_admin_cannot_disable_their_own_account(admin: httpx.AsyncClient, db_session: AsyncSession) -> None:
    root = await db_session.scalar(sa.select(User).where(User.username == "root"))
    assert root is not None
    db_session.add(User(username="second", is_admin=True))
    await db_session.flush()

    response = await admin.patch(f"/api/admin/users/{root.id}", json={"is_active": False}, headers=xsrf(admin))

    assert (response.status_code, response.json()["detail"]) == (
        fastapi.status.HTTP_409_CONFLICT,
        "You cannot disable your own account",
    )
    assert root.is_active


async def test_the_last_active_admin_cannot_be_disabled(db_session: AsyncSession, create_user: CreateUser) -> None:
    root = await create_user("root", is_admin=True)

    with pytest.raises(LastAdminError):
        await AccountManager(db_session).set_active(root, active=False)


async def test_two_admins_disabling_each_other_leave_one_active(database: DatabaseManager) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as setup:
        first, _ = await AccountManager(setup).create_user("race-a", is_admin=True, now=dt.datetime.now(dt.UTC))
        second, _ = await AccountManager(setup).create_user("race-b", is_admin=True, now=dt.datetime.now(dt.UTC))
        await setup.commit()

    async def disable(user_id: object) -> bool:
        async with AsyncSession(database.engine) as session:
            user = await session.get(User, user_id)
            assert user is not None
            try:
                await AccountManager(session).set_active(user, active=False)
            except LastAdminError:
                return False
            await asyncio.sleep(0.05)
            await session.commit()
            return True

    try:
        results = await asyncio.gather(disable(first.id), disable(second.id))
        assert sorted(results) == [False, True]
    finally:
        async with AsyncSession(database.engine) as cleanup:
            await cleanup.execute(sa.delete(User).where(User.id.in_([first.id, second.id])))
            await cleanup.commit()
