"""A fake browser push service and devices, shared by the push tests as fixtures."""

import dataclasses
import json

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mintrack.config import SecurityConfig
from mintrack.core.push.webpush import VAPID_KEY_PURPOSE, Subscription, VapidKey, b64url_encode

SECRET_KEY = "0123456789abcdef0123456789abcdef"
VAPID_SUBJECT = "https://mintrack.test"


def vapid_key_for(secret: str, subject: str = VAPID_SUBJECT) -> VapidKey:
    return VapidKey(SecurityConfig(secret_key=secret).derive_key(VAPID_KEY_PURPOSE), subject)


@dataclasses.dataclass
class Device:
    """A browser's side of a push subscription: it can decrypt what it receives."""

    endpoint: str
    private_key: ec.EllipticCurvePrivateKey = dataclasses.field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    auth_secret: bytes = b"0123456789abcdef"

    @property
    def subscription(self) -> Subscription:
        public = self.private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return Subscription(endpoint=self.endpoint, p256dh=b64url_encode(public), auth=b64url_encode(self.auth_secret))

    def as_json(self) -> dict:
        subscription = self.subscription
        return {"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}}

    def decrypt(self, body: bytes) -> dict:
        plain = http_ece.decrypt(body, private_key=self.private_key, auth_secret=self.auth_secret, version="aes128gcm")
        return json.loads(plain)


class FakePushService:
    """A push service recording what it receives; it answers `status`, or `statuses[endpoint]` when set."""

    def __init__(self) -> None:
        self.status = 201
        self.statuses: dict[str, int] = {}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.statuses.get(str(request.url), self.status))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def received_by(self, device: Device) -> list[dict]:
        return [device.decrypt(request.content) for request in self.requests if str(request.url) == device.endpoint]


@pytest.fixture
def vapid_key() -> VapidKey:
    return vapid_key_for(SECRET_KEY)


@pytest.fixture
def push_service() -> FakePushService:
    return FakePushService()


@pytest.fixture
def device() -> Device:
    return Device("https://fcm.googleapis.com/fcm/send/device-1")
