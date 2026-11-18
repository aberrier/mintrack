import collections.abc
import datetime as dt
import typing

import fastapi
import httpx
import pydantic
from cryptography.hazmat.primitives.asymmetric import ec

from mintrack.core.push.managers import PushManager
from mintrack.core.push.webpush import (
    SendResult,
    Subscription,
    VapidKey,
    b64url_decode,
    get_vapid_key,
    is_push_service,
    push_client,
)
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import WITHOUT_NUL, CurrentSessionDepType, CurrentUserDepType

router = fastapi.APIRouter(prefix="/push", tags=["push"])

AUTH_SECRET_LENGTH = 16
ENDPOINT_MAX_LENGTH = 2048


def _decoded(value: str) -> bytes:
    try:
        return b64url_decode(value)
    except ValueError:
        msg = "must be base64url"
        raise ValueError(msg) from None


def _push_endpoint(value: str) -> str:
    if not is_push_service(value):
        msg = "must be the https address of a known browser push service"
        raise ValueError(msg)
    return value


def _p256_point(value: str) -> str:
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _decoded(value))
    except ValueError:
        msg = "must be a P-256 public key"
        raise ValueError(msg) from None
    return value


def _auth_secret(value: str) -> str:
    if len(_decoded(value)) != AUTH_SECRET_LENGTH:
        msg = f"must be {AUTH_SECRET_LENGTH} bytes"
        raise ValueError(msg)
    return value


Endpoint = typing.Annotated[
    str,
    pydantic.Field(max_length=ENDPOINT_MAX_LENGTH, pattern=WITHOUT_NUL),
    pydantic.AfterValidator(_push_endpoint),
]


class VapidKeyResponse(pydantic.BaseModel):
    public_key: str | None


class SubscriptionKeys(pydantic.BaseModel):
    p256dh: typing.Annotated[str, pydantic.Field(max_length=128), pydantic.AfterValidator(_p256_point)]
    auth: typing.Annotated[str, pydantic.Field(max_length=64), pydantic.AfterValidator(_auth_secret)]


class SubscriptionRequest(pydantic.BaseModel):
    """A browser's `PushSubscription.toJSON()`."""

    endpoint: Endpoint
    keys: SubscriptionKeys


class DeviceRequest(pydantic.BaseModel):
    endpoint: Endpoint


OptionalVapidKeyDepType = typing.Annotated[VapidKey | None, fastapi.Depends(get_vapid_key)]


async def get_push_client() -> collections.abc.AsyncGenerator[httpx.AsyncClient]:
    async with push_client() as client:
        yield client


async def get_push_manager(
    session: DbSessionDepType,
    key: OptionalVapidKeyDepType,
    client: typing.Annotated[httpx.AsyncClient, fastapi.Depends(get_push_client)],
) -> PushManager:
    if key is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "Push notifications are not configured")
    return PushManager(session, client, key)


PushManagerDepType = typing.Annotated[PushManager, fastapi.Depends(get_push_manager)]


@router.get("/key")
async def get_public_key(key: OptionalVapidKeyDepType) -> VapidKeyResponse:
    """The server's public key; null when this server cannot send push."""
    return VapidKeyResponse(public_key=key.public_key if key else None)


@router.post("/subscriptions", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def subscribe(body: SubscriptionRequest, current: CurrentSessionDepType, manager: PushManagerDepType) -> None:
    """Register this device; signing out on it removes it."""
    subscription = Subscription(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth)
    await manager.subscribe(current.user, subscription, dt.datetime.now(dt.UTC), session_id=current.session_id)


@router.delete("/subscriptions", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unsubscribe(body: DeviceRequest, user: CurrentUserDepType, manager: PushManagerDepType) -> None:
    await manager.unsubscribe(user, body.endpoint)


@router.post(
    "/test",
    status_code=fastapi.status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "This device is not registered"}, 502: {"description": "The push service failed"}},
)
async def send_test(body: DeviceRequest, user: CurrentUserDepType, manager: PushManagerDepType) -> None:
    result = await manager.send_test(user, body.endpoint, dt.datetime.now(dt.UTC))
    if result is None or result is SendResult.GONE:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "This device is not registered")
    if result is SendResult.FAILED:
        raise fastapi.HTTPException(fastapi.status.HTTP_502_BAD_GATEWAY, "The push service did not accept the message")
