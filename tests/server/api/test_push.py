import collections.abc

import fastapi
import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.push.webpush import VapidKey, get_vapid_key
from mintrack.db.models import PushSubscription
from mintrack.server.api.push import get_push_client
from tests.push_service import Device, FakePushService


@pytest_asyncio.fixture
async def push_app(api_app: fastapi.FastAPI, vapid_key: VapidKey, push_service: FakePushService) -> fastapi.FastAPI:
    """The API with push set up, sending to the fake push service."""

    async def push_client() -> collections.abc.AsyncGenerator[httpx.AsyncClient]:
        async with push_service.client() as client:
            yield client

    api_app.dependency_overrides[get_vapid_key] = lambda: vapid_key
    api_app.dependency_overrides[get_push_client] = push_client
    return api_app


async def endpoints(db_session: AsyncSession) -> list[str]:
    return list(await db_session.scalars(sa.select(PushSubscription.endpoint)))


async def test_without_push_the_key_is_null_and_devices_cannot_subscribe(
    signed_in: httpx.AsyncClient, device: Device
) -> None:
    get_vapid_key.cache_clear()

    key = await signed_in.get("/api/push/key")
    subscription = await signed_in.post("/api/push/subscriptions", json=device.as_json())

    assert key.json() == {"public_key": None}
    assert subscription.status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_the_public_key_is_the_derived_one(
    push_app: fastapi.FastAPI, signed_in: httpx.AsyncClient, vapid_key: VapidKey
) -> None:
    response = await signed_in.get("/api/push/key")

    assert response.json() == {"public_key": vapid_key.public_key}


async def test_a_device_subscribes_tests_and_unsubscribes(
    push_app: fastapi.FastAPI,
    signed_in: httpx.AsyncClient,
    db_session: AsyncSession,
    push_service: FakePushService,
    device: Device,
) -> None:
    assert (await signed_in.post("/api/push/subscriptions", json=device.as_json())).status_code == 204
    assert (await signed_in.post("/api/push/subscriptions", json=device.as_json())).status_code == 204
    assert await endpoints(db_session) == [device.endpoint]

    assert (await signed_in.post("/api/push/test", json={"endpoint": device.endpoint})).status_code == 204
    [message] = push_service.received_by(device)
    assert message["notification"]["title"] == "MinTrack"

    response = await signed_in.request("DELETE", "/api/push/subscriptions", json={"endpoint": device.endpoint})
    assert response.status_code == 204
    assert await endpoints(db_session) == []


async def test_testing_an_unknown_device_answers_404(
    push_app: fastapi.FastAPI, signed_in: httpx.AsyncClient, device: Device
) -> None:
    response = await signed_in.post("/api/push/test", json={"endpoint": device.endpoint})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_an_expired_device_is_deleted_when_tested(
    push_app: fastapi.FastAPI,
    signed_in: httpx.AsyncClient,
    db_session: AsyncSession,
    push_service: FakePushService,
    device: Device,
) -> None:
    await signed_in.post("/api/push/subscriptions", json=device.as_json())
    push_service.status = 410

    response = await signed_in.post("/api/push/test", json={"endpoint": device.endpoint})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert await endpoints(db_session) == []


async def test_a_push_service_failure_answers_502(
    push_app: fastapi.FastAPI, signed_in: httpx.AsyncClient, push_service: FakePushService, device: Device
) -> None:
    await signed_in.post("/api/push/subscriptions", json=device.as_json())
    push_service.status = 500

    response = await signed_in.post("/api/push/test", json={"endpoint": device.endpoint})

    assert response.status_code == fastapi.status.HTTP_502_BAD_GATEWAY


@pytest.mark.parametrize(
    "change",
    [
        ("endpoint", "https://169.254.169.254/latest/meta-data"),
        ("endpoint", "http://fcm.googleapis.com/fcm/send/x"),
        ("endpoint", "https://fcm.googleapis.com/" + "x" * 2048),
        ("p256dh", "BAAA"),
        ("p256dh", "not base64 !"),
        ("auth", "c2hvcnQ"),
    ],
)
async def test_invalid_subscriptions_are_refused(
    push_app: fastapi.FastAPI,
    signed_in: httpx.AsyncClient,
    db_session: AsyncSession,
    device: Device,
    change: tuple[str, str],
) -> None:
    field, value = change
    body = device.as_json()
    if field == "endpoint":
        body["endpoint"] = value
    else:
        body["keys"][field] = value

    response = await signed_in.post("/api/push/subscriptions", json=body)

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await endpoints(db_session) == []
