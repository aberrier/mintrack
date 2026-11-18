import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Every request body but an import upload: JSON forms and lists of episode ids.
MAX_BODY_BYTES = 1024 * 1024


class _BodyTooLargeError(Exception):
    pass


class _Exchange:
    """One request's receive and send, counting the body against the limit."""

    def __init__(self, receive: Receive, send: Send, limit: int) -> None:
        self._receive = receive
        self._send = send
        self.limit = limit
        self.received = 0
        self.exceeded = False
        self.started = False

    async def receive(self) -> Message:
        message = await self._receive()
        if message["type"] == "http.request":
            self.received += len(message.get("body", b""))
            if self.received > self.limit:
                self.exceeded = True
                raise _BodyTooLargeError
        return message

    async def send(self, message: Message) -> None:
        # Once the body is over the limit, the app's own answer to the interruption (a 500) is replaced.
        if self.exceeded and not self.started:
            return
        self.started = self.started or message["type"] == "http.response.start"
        await self._send(message)


class BodySizeLimitMiddleware:
    """Answer 413 to a request body over its limit, whether announced by Content-Length or streamed without it,
    before the app reads it all into memory. `limits` maps path prefixes to other limits."""

    def __init__(self, app: ASGIApp, *, limits: dict[str, int]) -> None:
        self.app = app
        self.limits = limits

    def _limit(self, path: str) -> int:
        return next((limit for prefix, limit in self.limits.items() if path.startswith(prefix)), MAX_BODY_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["path"])
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            await _too_large(send)
            return
        exchange = _Exchange(receive, send, limit)
        try:
            await self.app(scope, exchange.receive, exchange.send)
        except Exception:
            if not exchange.exceeded or exchange.started:
                raise
        if exchange.exceeded and not exchange.started:
            await _too_large(send)


async def _too_large(send: Send) -> None:
    body = json.dumps({"detail": "The request body is too large."}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
