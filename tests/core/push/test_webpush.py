import datetime as dt
import json

import httpx
import py_vapid
import pytest

from mintrack.config import get_config
from mintrack.core.push.webpush import SendResult, VapidKey, b64url_decode, get_vapid_key, is_push_service, send
from tests.push_service import SECRET_KEY, VAPID_SUBJECT, Device, FakePushService, vapid_key_for

NOW = dt.datetime(2026, 11, 18, 20, 0, tzinfo=dt.UTC)


def jwt_claims(authorization: str) -> dict:
    token = authorization.split("t=")[1].split(",", maxsplit=1)[0]
    return json.loads(b64url_decode(token.split(".")[1]))


def test_the_key_is_derived_from_the_secret_key() -> None:
    assert vapid_key_for(SECRET_KEY).public_key == vapid_key_for(SECRET_KEY).public_key
    assert vapid_key_for(SECRET_KEY).public_key != vapid_key_for(SECRET_KEY + "x").public_key


@pytest.mark.parametrize(
    ("secret_key", "public_url", "subject"),
    [
        (None, "https://tv.example.com", None),
        (SECRET_KEY, "http://tv.example.com", None),
        (SECRET_KEY, "https://tv.example.com", "https://tv.example.com"),
        (SECRET_KEY, "https://tv.example.com:8443/", "https://tv.example.com:8443"),
    ],
)
def test_push_needs_a_secret_key_and_an_https_public_url(
    env: pytest.MonkeyPatch, secret_key: str | None, public_url: str, subject: str | None
) -> None:
    if secret_key:
        env.setenv("MINTRACK__SECURITY__SECRET_KEY", secret_key)
    env.setenv("MINTRACK__PROJECT__PUBLIC_URL", public_url)
    get_config.cache_clear()
    get_vapid_key.cache_clear()
    try:
        key = get_vapid_key()
    finally:
        get_vapid_key.cache_clear()

    assert (key and key.subject) == subject
    if key:
        assert key.public_key == vapid_key_for(SECRET_KEY).public_key


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
    ],
)
def test_browser_push_services_are_reachable(endpoint: str) -> None:
    assert is_push_service(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com:8443/fcm/send/abc",
        "https://user@fcm.googleapis.com/fcm/send/abc",
        "https://evilfcm.googleapis.com.example.com/abc",
        "https://push.apple.com.example.com/abc",
        "https://localhost/abc",
        "https://10.0.0.1/abc",
        "not a url",
    ],
)
def test_other_addresses_are_not(endpoint: str) -> None:
    assert not is_push_service(endpoint)


async def test_a_message_is_encrypted_for_the_device_and_signed_by_the_server(
    vapid_key: VapidKey, push_service: FakePushService, device: Device
) -> None:
    async with push_service.client() as client:
        result = await send(client, vapid_key, device.subscription, b'{"hello": "world"}', NOW)

    assert result is SendResult.SENT
    [request] = push_service.requests
    assert device.decrypt(request.content) == {"hello": "world"}
    assert request.headers["Content-Encoding"] == "aes128gcm"
    assert request.headers["TTL"] == "86400"
    authorization = request.headers["Authorization"]
    assert py_vapid.Vapid02.verify(authorization)
    assert f"k={vapid_key.public_key}" in authorization
    assert jwt_claims(authorization) == {
        "aud": "https://fcm.googleapis.com",
        "exp": int((NOW + dt.timedelta(hours=12)).timestamp()),
        "sub": VAPID_SUBJECT,
    }


@pytest.mark.parametrize(
    ("status", "expected"), [(404, SendResult.GONE), (410, SendResult.GONE), (429, SendResult.FAILED)]
)
async def test_the_push_service_answer_decides_the_result(
    vapid_key: VapidKey, push_service: FakePushService, device: Device, status: int, expected: SendResult
) -> None:
    push_service.status = status

    async with push_service.client() as client:
        assert await send(client, vapid_key, device.subscription, b"{}", NOW) is expected


async def test_a_network_error_is_a_failure(vapid_key: VapidKey, device: Device) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        message = "timeout"
        raise httpx.ConnectTimeout(message, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        assert await send(client, vapid_key, device.subscription, b"{}", NOW) is SendResult.FAILED


async def test_an_endpoint_outside_the_push_services_is_never_called(
    vapid_key: VapidKey, push_service: FakePushService
) -> None:
    device = Device("https://192.168.1.10/internal")

    async with push_service.client() as client:
        assert await send(client, vapid_key, device.subscription, b"{}", NOW) is SendResult.GONE
    assert push_service.requests == []
