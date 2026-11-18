import asyncio
import ipaddress
import uuid

import httpx
import pytest
import respx

from mintrack.integrations.jellyfin import client as jellyfin_client
from mintrack.integrations.jellyfin.client import (
    ForbiddenAddressError,
    JellyfinClient,
    JellyfinError,
    JellyfinRedirectError,
    JellyfinUnauthorizedError,
    JellyfinUnreachableError,
    is_forbidden_address,
)

URL = "http://127.0.0.1:8096/jellyfin"
DEVICE = uuid.UUID(int=1)


@pytest.mark.parametrize("address", ["192.168.1.10", "10.0.0.2", "127.0.0.1", "::1", "93.184.216.34"])
def test_lan_loopback_and_public_addresses_are_allowed(address: str) -> None:
    assert not is_forbidden_address(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "::ffff:169.254.169.254", "fd00:ec2::254", "0.0.0.0", "224.0.0.1", "240.0.0.1"]
)
def test_addresses_no_media_server_lives_at_are_forbidden(address: str) -> None:
    assert is_forbidden_address(ipaddress.ip_address(address))


async def test_a_forbidden_address_is_refused_before_any_request(respx_mock: respx.Router) -> None:
    with pytest.raises(ForbiddenAddressError):
        async with JellyfinClient("http://169.254.169.254", device_id=DEVICE):
            pass
    assert not respx_mock.calls


async def test_requests_identify_the_device_and_carry_the_token_under_the_server_path(
    respx_mock: respx.Router,
) -> None:
    route = respx_mock.post(f"{URL}/Sessions/Logout").respond(204)

    async with JellyfinClient(URL, device_id=DEVICE, token="t0ken") as client:
        await client.logout()

    authorization = route.calls.last.request.headers["Authorization"]
    assert authorization.startswith('MediaBrowser Client="MinTrack", Device="MinTrack", DeviceId="')
    assert f'DeviceId="{DEVICE}"' in authorization
    assert authorization.endswith(', Token="t0ken"')


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401), JellyfinUnauthorizedError),
        (httpx.Response(403), JellyfinUnauthorizedError),
        (httpx.Response(502), JellyfinUnreachableError),
        (httpx.Response(302, headers={"Location": "https://elsewhere/"}), JellyfinRedirectError),
        (httpx.Response(404), JellyfinError),
        (httpx.Response(200, text="<html>not jellyfin</html>"), JellyfinError),
        (httpx.ConnectError("refused"), JellyfinUnreachableError),
        (httpx.ReadTimeout("slow"), JellyfinUnreachableError),
    ],
)
async def test_failures_map_to_errors_the_user_can_act_on(
    respx_mock: respx.Router, response: httpx.Response | Exception, error: type[JellyfinError]
) -> None:
    respx_mock.post(f"{URL}/Users/AuthenticateByName").mock(side_effect=[response])

    with pytest.raises(error):
        async with JellyfinClient(URL, device_id=DEVICE) as client:
            await client.authenticate("bob", "secret")


async def test_an_oversized_response_is_refused(respx_mock: respx.Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jellyfin_client, "MAX_RESPONSE_BYTES", 10)
    respx_mock.get(f"{URL}/Items").respond(200, json={"Items": [], "TotalRecordCount": 0})

    with pytest.raises(JellyfinError, match="too large"):
        async with JellyfinClient(URL, device_id=DEVICE, token="t") as client:
            await client.played_items("u", 0)


async def test_items_are_fetched_in_batches_of_ids(respx_mock: respx.Router) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["Ids"].split(",")
        return httpx.Response(200, json={"Items": [{"Id": i, "Type": "Series"} for i in ids], "TotalRecordCount": 1})

    route = respx_mock.get(f"{URL}/Items").mock(side_effect=answer)

    async with JellyfinClient(URL, device_id=DEVICE, token="t") as client:
        items = await client.items("u", {f"s{n:03}" for n in range(150)})

    assert len(items) == 150
    assert route.call_count == 2


async def test_a_server_answering_too_slowly_counts_as_unreachable(
    respx_mock: respx.Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jellyfin_client, "TOTAL_TIMEOUT_SECONDS", 0.05)

    async def drip(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    respx_mock.get(f"{URL}/Items").mock(side_effect=drip)

    with pytest.raises(JellyfinUnreachableError):
        async with JellyfinClient(URL, device_id=DEVICE, token="t") as client:
            await client.played_items("u", 0)
