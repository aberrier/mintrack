import pathlib
import re

import fastapi
import fastapi.responses
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

# Paths owned by the backend: they never fall back to the app.
RESERVED_PREFIXES = ("/api", "/mcp", "/.well-known")
# Angular's output hashing: main-72OG7TZP.js, chunk-D24BMUA5.js, styles-VTGUK7AB.css.
HASHED_NAME = re.compile(r"-[A-Z0-9]{8}\.[a-z0-9]+$")

IMMUTABLE = "public, max-age=31536000, immutable"
# Everything without a hashed name (index.html, the manifest, service worker files) is revalidated on every load.
REVALIDATE = "no-cache"


def _is_reserved(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in RESERVED_PREFIXES)


def _not_found() -> fastapi.Response:
    return fastapi.responses.JSONResponse({"detail": "Not Found"}, status_code=fastapi.status.HTTP_404_NOT_FOUND)


def install_frontend(app: fastapi.FastAPI, dist: pathlib.Path) -> None:
    """Serve the built app from `dist` behind every API route.

    A GET that matches a file gets the file; one whose last segment has no extension gets index.html, so client
    routes such as /shows/42 load the app; anything else is a 404, so a stale tab asking for a deleted chunk gets
    an error instead of HTML.
    """
    files = StaticFiles(directory=dist, follow_symlink=False)

    async def serve(request: fastapi.Request) -> fastapi.Response:
        url_path = request.url.path
        path = url_path.removeprefix("/")
        if _is_reserved(url_path):
            return _not_found()
        if request.method not in {"GET", "HEAD"}:
            return fastapi.responses.JSONResponse(
                {"detail": "Method Not Allowed"}, status_code=fastapi.status.HTTP_405_METHOD_NOT_ALLOWED
            )
        segments = [segment for segment in path.split("/") if segment]
        # Hidden files (.env, .git...) and any ".." never resolve, whatever the encoding of the request.
        if any(segment.startswith(".") for segment in segments):
            return _not_found()

        try:
            response = await files.get_response(path or "index.html", request.scope)
            name = segments[-1] if segments else "index.html"
        except HTTPException as error:
            if error.status_code != fastapi.status.HTTP_404_NOT_FOUND or (segments and "." in segments[-1]):
                return _not_found()
            response = await files.get_response("index.html", request.scope)
            name = "index.html"

        response.headers["Cache-Control"] = IMMUTABLE if HASHED_NAME.search(name) else REVALIDATE
        return response

    fallback = app.router.default

    async def default(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await fallback(scope, receive, send)
            return
        response = await serve(fastapi.Request(scope, receive))
        await response(scope, receive, send)

    # The router's default runs only when no route matches at all, not even by path with another method: a wrong
    # method on an API route keeps its 405 and Allow header.
    app.router.default = default
