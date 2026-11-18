import base64
import dataclasses
import datetime as dt
import enum
import functools
import urllib.parse

import http_ece
import httpx
import py_vapid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mintrack.config import get_config
from mintrack.observability.logging import logger

# Order of the P-256 group: private keys are integers in [1, order - 1].
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
VAPID_KEY_PURPOSE = b"mintrack web push vapid"
# Push services reject a VAPID token valid for more than 24 hours.
VAPID_TOKEN_LIFETIME = dt.timedelta(hours=12)
# Seconds a push service keeps an undelivered message.
MESSAGE_TTL = 86400
REQUEST_TIMEOUT_SECONDS = 10
# The push services of Chrome and other Chromium browsers, Firefox, Safari and Edge. Requests go only there, so an
# endpoint cannot point the server at an internal address.
PUSH_SERVICE_HOSTS = ("fcm.googleapis.com", ".push.services.mozilla.com", ".push.apple.com", ".notify.windows.com")
# Answers meaning the subscription no longer exists.
GONE_STATUSES = {404, 410}


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def is_push_service(endpoint: str) -> bool:
    url = urllib.parse.urlsplit(endpoint)
    host = (url.hostname or "").lower()
    if url.scheme != "https" or url.port not in {None, 443} or url.username or url.password:
        return False
    return any(host == suffix or (suffix.startswith(".") and host.endswith(suffix)) for suffix in PUSH_SERVICE_HOSTS)


class VapidKey:
    """The server's Web Push identity (RFC 8292), derived from the secret key."""

    def __init__(self, seed: bytes, subject: str) -> None:
        scalar = int.from_bytes(seed) % (P256_ORDER - 1) + 1
        self._vapid = py_vapid.Vapid02(ec.derive_private_key(scalar, ec.SECP256R1()), conf={"no-strict": True})
        self.subject = subject
        public_point = self._vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.public_key = b64url_encode(public_point)

    def authorization(self, endpoint: str, now: dt.datetime) -> str:
        url = urllib.parse.urlsplit(endpoint)
        claims = {
            "aud": f"{url.scheme}://{url.netloc}",
            "exp": int((now + VAPID_TOKEN_LIFETIME).timestamp()),
            "sub": self.subject,
        }
        return self._vapid.sign(claims)["Authorization"]


@functools.cache
def get_vapid_key() -> VapidKey | None:
    """The VAPID key, or None when push is unavailable: no secret key, or a public URL that is not https.

    Browsers only offer push to secure pages, and push services want an https subject.
    """
    config = get_config()
    if config.security.secret_key is None or config.project.public_url.scheme != "https":
        return None
    return VapidKey(config.security.derive_key(VAPID_KEY_PURPOSE), config.project.public_origin)


@dataclasses.dataclass(frozen=True)
class Subscription:
    endpoint: str
    p256dh: str
    auth: str


class SendResult(enum.StrEnum):
    SENT = enum.auto()
    GONE = enum.auto()
    FAILED = enum.auto()


def encrypt(subscription: Subscription, payload: bytes) -> bytes:
    """Encrypt for the subscriber with a one-time key (RFC 8291, aes128gcm)."""
    return http_ece.encrypt(
        payload,
        private_key=ec.generate_private_key(ec.SECP256R1()),
        dh=b64url_decode(subscription.p256dh),
        auth_secret=b64url_decode(subscription.auth),
        version="aes128gcm",
    )


async def send(
    client: httpx.AsyncClient, key: VapidKey, subscription: Subscription, payload: bytes, now: dt.datetime
) -> SendResult:
    if not is_push_service(subscription.endpoint):
        return SendResult.GONE
    headers = {
        "Authorization": key.authorization(subscription.endpoint, now),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(MESSAGE_TTL),
    }
    try:
        response = await client.post(
            subscription.endpoint,
            content=encrypt(subscription, payload),
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        logger.warning("push request failed", error=type(error).__name__)
        return SendResult.FAILED
    if response.status_code in GONE_STATUSES:
        return SendResult.GONE
    if not response.is_success:
        logger.warning("push service refused a message", status=response.status_code)
        return SendResult.FAILED
    return SendResult.SENT
