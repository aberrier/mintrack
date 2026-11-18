import fastapi
import fastapi.responses
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class GenericServerErrorMiddleware:
    """Answer unhandled errors with a generic 500 that still goes through our other middlewares.

    Starlette's own handler sits outside every middleware, so its 500 would lack the security headers.
    The exception is re-raised afterwards: uvicorn logs it and Sentry (when enabled) captures it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            response_started = response_started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            if not response_started:
                response = fastapi.responses.JSONResponse(
                    status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Internal Server Error"},
                )
                await response(scope, receive, send)
            raise
