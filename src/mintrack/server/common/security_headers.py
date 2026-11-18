from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mintrack.server.common.config import API_PREFIX

# 'unsafe-inline' styles: Angular and Material inject styles at runtime. Scripts stay strict.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://image.tmdb.org; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    # Trusted Types: only Angular's sanitiser and Material's icon loader may create HTML from strings.
    "require-trusted-types-for 'script'; "
    "trusted-types angular angular#unsafe-bypass angular#components"
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware:
    """Add the security headers to every HTTP response, and the CSP to HTML ones.

    HSTS is left to the HTTPS reverse proxy: MinTrack also runs over plain HTTP.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                # The only HTML under /api is the development API docs page, which loads Swagger UI from a CDN.
                is_app_page = not scope["path"].startswith(API_PREFIX + "/")
                if is_app_page and headers.get("content-type", "").startswith("text/html"):
                    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            await send(message)

        await self.app(scope, receive, send_with_headers)
