import uuid

import httpx
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import JellyfinAccount
from tests.fakes.jellyfin import SERVER_URL, FakeJellyfin
from tests.server.api.conftest import CreateUser, log_in, xsrf

ACCOUNTS = "/api/jellyfin/accounts"


class Profile:
    """What a signed-in user does with Jellyfin on their profile, through the API."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def link(
        self, username: str = "bob", password: str = "secret", server_url: str = SERVER_URL
    ) -> httpx.Response:
        payload = {"server_url": server_url, "username": username, "password": password}
        return await self.client.post(ACCOUNTS, json=payload)

    async def accounts(self) -> list[dict]:
        response = await self.client.get(ACCOUNTS)
        assert response.status_code == 200
        return response.json()


@pytest.fixture
def profile(signed_in: httpx.AsyncClient) -> Profile:
    return Profile(signed_in)


async def queued_syncs(session: AsyncSession) -> list[dict]:
    jobs = await session.scalars(
        sa.text("SELECT args FROM procrastinate_jobs WHERE task_name = 'mintrack:jellyfin.sync_account' ORDER BY id")
    )
    return list(jobs)


@pytest.fixture
def bob(jellyfin: FakeJellyfin) -> None:
    jellyfin.add_user("bob", "secret")


async def test_user_links_a_jellyfin_account_and_a_first_sync_is_queued(
    profile: Profile, jellyfin: FakeJellyfin, bob: None, db_session: AsyncSession
) -> None:
    response = await profile.link(server_url=f"{SERVER_URL}/")

    assert response.status_code == 201
    account = response.json()
    assert account | {"id": None} == {
        "id": None,
        "server_url": SERVER_URL,
        "username": "bob",
        "last_sync_at": None,
        "last_success_at": None,
        "last_sync_status": None,
        "last_sync_imported": 0,
        "last_sync_skipped": 0,
    }
    assert await profile.accounts() == [account]
    assert await queued_syncs(db_session) == [{"account_id": account["id"], "full": False}]
    stored = await db_session.get_one(JellyfinAccount, uuid.UUID(account["id"]))
    assert stored.token in jellyfin.tokens


@pytest.mark.parametrize(
    ("server_url", "password", "fake_answer", "status", "detail"),
    [
        (SERVER_URL, "wrong", None, 400, "jellyfin_invalid_credentials"),
        # The same answer as an unreachable server: errors tell nothing about the network.
        ("http://169.254.169.254", "secret", None, 502, "jellyfin_unreachable"),
        (SERVER_URL, "secret", httpx.ConnectError("refused"), 502, "jellyfin_unreachable"),
        (SERVER_URL, "secret", httpx.Response(301, headers={"Location": "https://jf/"}), 502, "jellyfin_redirected"),
        (SERVER_URL, "secret", httpx.Response(200, text="<html>"), 502, "jellyfin_bad_response"),
        (
            SERVER_URL,
            "secret",
            httpx.Response(200, json={"AccessToken": "t", "ServerId": "s", "User": {"Id": "u", "Name": "b\x00ob"}}),
            502,
            "jellyfin_bad_response",
        ),
    ],
)
async def test_link_errors_say_what_to_fix_and_store_nothing(
    profile: Profile,
    jellyfin: FakeJellyfin,
    bob: None,
    respx_mock: respx.Router,
    server_url: str,
    password: str,
    fake_answer: httpx.Response | Exception | None,
    status: int,
    detail: str,
) -> None:
    if fake_answer is not None:
        respx_mock.post(f"{SERVER_URL}/Users/AuthenticateByName").mock(side_effect=[fake_answer])

    response = await profile.link(password=password, server_url=server_url)

    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert await profile.accounts() == []


async def test_a_server_that_is_not_jellyfin_answers_as_unreachable_whatever_it_says(
    profile: Profile, jellyfin: FakeJellyfin, bob: None
) -> None:
    jellyfin.is_jellyfin = False

    wrong_password = await profile.link(password="wrong")
    quick_connect = await profile.client.post("/api/jellyfin/quick-connect", json={"server_url": SERVER_URL})

    assert wrong_password.json() == quick_connect.json() == {"detail": "jellyfin_unreachable"}


async def test_requests_to_server_addresses_are_limited_per_user(profile: Profile, jellyfin: FakeJellyfin) -> None:
    statuses = [(await profile.link(password="wrong")).status_code for _ in range(31)]

    assert statuses == [400] * 30 + [429]


@pytest.mark.parametrize("server_url", ["ftp://jf", "http://user:pw@jf", "http://jf/?a=1", "jf.local"])
async def test_a_server_url_must_be_a_plain_http_address(profile: Profile, server_url: str) -> None:
    assert (await profile.link(server_url=server_url)).status_code == 422


async def test_linking_again_replaces_the_token_and_keeps_one_account(
    profile: Profile, jellyfin: FakeJellyfin, bob: None
) -> None:
    first = (await profile.link()).json()

    second = await profile.link()

    assert second.json()["id"] == first["id"]
    assert len(await profile.accounts()) == 1
    # Same device, same Jellyfin user: the server ended the first session.
    assert len(jellyfin.tokens) == 1


async def test_user_unlinks_an_account_and_its_token_is_revoked(
    profile: Profile, jellyfin: FakeJellyfin, bob: None
) -> None:
    account = (await profile.link()).json()

    response = await profile.client.delete(f"{ACCOUNTS}/{account['id']}")

    assert response.status_code == 204
    assert await profile.accounts() == []
    assert jellyfin.tokens == {}


async def test_unlinking_works_when_the_server_is_gone(
    profile: Profile, jellyfin: FakeJellyfin, bob: None, respx_mock: respx.Router
) -> None:
    account = (await profile.link()).json()
    respx_mock.post(f"{SERVER_URL}/Sessions/Logout").mock(side_effect=httpx.ConnectError("gone"))

    assert (await profile.client.delete(f"{ACCOUNTS}/{account['id']}")).status_code == 204
    assert await profile.accounts() == []


async def test_sync_now_queues_a_full_sync_unless_one_is_waiting(
    profile: Profile, jellyfin: FakeJellyfin, bob: None, db_session: AsyncSession
) -> None:
    account = (await profile.link()).json()

    responses = [await profile.client.post(f"{ACCOUNTS}/{account['id']}/sync") for _ in range(2)]

    assert [response.status_code for response in responses] == [202, 202]
    assert [job["full"] for job in await queued_syncs(db_session)] == [False, True]


async def test_accounts_belong_to_their_user(
    profile: Profile,
    jellyfin: FakeJellyfin,
    bob: None,
    create_user: CreateUser,
) -> None:
    account = (await profile.link()).json()
    await create_user("mallory")
    await log_in(profile.client, "mallory")
    profile.client.headers.update(xsrf(profile.client))

    assert await profile.accounts() == []
    assert (await profile.client.delete(f"{ACCOUNTS}/{account['id']}")).status_code == 404
    assert (await profile.client.post(f"{ACCOUNTS}/{account['id']}/sync")).status_code == 404


async def test_user_links_an_account_with_quick_connect_once_approved_in_jellyfin(
    profile: Profile, jellyfin: FakeJellyfin, bob: None, db_session: AsyncSession
) -> None:
    started = await profile.client.post("/api/jellyfin/quick-connect", json={"server_url": SERVER_URL})
    assert started.status_code == 200
    request = {"server_url": SERVER_URL, "secret": started.json()["secret"]}

    waiting = await profile.client.post("/api/jellyfin/quick-connect/state", json=request)
    too_early = await profile.client.post("/api/jellyfin/accounts/quick-connect", json=request)
    jellyfin.approve(started.json()["code"], "bob")
    approved = await profile.client.post("/api/jellyfin/quick-connect/state", json=request)
    linked = await profile.client.post("/api/jellyfin/accounts/quick-connect", json=request)

    assert waiting.json() == {"approved": False}
    assert (too_early.status_code, too_early.json()) == (409, {"detail": "jellyfin_quick_connect_pending"})
    assert approved.json() == {"approved": True}
    assert linked.status_code == 201
    assert linked.json()["username"] == "bob"
    stored = await db_session.get_one(JellyfinAccount, uuid.UUID(linked.json()["id"]))
    assert stored.token in jellyfin.tokens
    assert await queued_syncs(db_session) == [{"account_id": linked.json()["id"], "full": False}]


async def test_quick_connect_turned_off_on_the_server_falls_back_to_the_password(
    profile: Profile, jellyfin: FakeJellyfin
) -> None:
    jellyfin.quick_connect = False

    response = await profile.client.post("/api/jellyfin/quick-connect", json={"server_url": SERVER_URL})

    assert (response.status_code, response.json()) == (400, {"detail": "jellyfin_quick_connect_disabled"})


async def test_quick_connect_refuses_forbidden_addresses(profile: Profile, respx_mock: respx.Router) -> None:
    response = await profile.client.post("/api/jellyfin/quick-connect", json={"server_url": "http://169.254.169.254"})

    assert (response.status_code, response.json()) == (502, {"detail": "jellyfin_unreachable"})
    assert not respx_mock.calls
