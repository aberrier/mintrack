import fastapi
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from mintrack.config import Config, get_config
from mintrack.server.api import admin_users, auth, catalog, push, tracking, upcoming
from mintrack.server.api.dependencies import check_xsrf, get_current_session
from mintrack.server.common import healthcheck
from mintrack.server.common.config import API_PREFIX, get_fastapi_common_config
from mintrack.server.common.exception_handlers import GenericServerErrorMiddleware
from mintrack.server.common.frontend import install_frontend
from mintrack.server.common.security_headers import SecurityHeadersMiddleware


def build_api_router() -> fastapi.APIRouter:
    router = fastapi.APIRouter(prefix=API_PREFIX)
    router.include_router(healthcheck.router)
    router.include_router(auth.public_router)

    # Every other route needs a session, and an XSRF token on unsafe methods.
    protected = fastapi.APIRouter(
        dependencies=[fastapi.Depends(get_current_session), fastapi.Depends(check_xsrf)],
        responses={
            fastapi.status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
            fastapi.status.HTTP_403_FORBIDDEN: {"description": "Missing XSRF token, or admins only"},
        },
    )
    protected.include_router(auth.router)
    protected.include_router(admin_users.router)
    protected.include_router(catalog.router)
    protected.include_router(tracking.router)
    protected.include_router(upcoming.router)
    protected.include_router(push.router)
    router.include_router(protected)
    return router


def build_app(config: Config | None = None) -> fastapi.FastAPI:
    """Build the ASGI app; `config` shapes its options and middlewares, the database stays `get_database()`'s."""
    config = config or get_config()

    app = fastapi.FastAPI(**get_fastapi_common_config(config))
    app.include_router(build_api_router())
    if config.server.frontend_dist is not None:
        # The app answers only what no route matches (the router's default).
        install_frontend(app, config.server.frontend_dist)
    app.add_middleware(GenericServerErrorMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)
    # Only the configured peers are trusted; uvicorn's own proxy handling is off (see the server command).
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=config.server.trusted_proxies)

    return app
