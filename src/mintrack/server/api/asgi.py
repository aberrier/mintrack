import fastapi
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from mintrack.config import Config, get_config
from mintrack.server.common import healthcheck
from mintrack.server.common.config import API_PREFIX, get_fastapi_common_config
from mintrack.server.common.exception_handlers import GenericServerErrorMiddleware
from mintrack.server.common.security_headers import SecurityHeadersMiddleware


def build_api_router() -> fastapi.APIRouter:
    router = fastapi.APIRouter(prefix=API_PREFIX)
    router.include_router(healthcheck.router)
    return router


def build_app(config: Config | None = None) -> fastapi.FastAPI:
    """Build the ASGI app; `config` shapes its options and middlewares, the database stays `get_database()`'s."""
    config = config or get_config()

    app = fastapi.FastAPI(**get_fastapi_common_config(config))
    app.include_router(build_api_router())
    app.add_middleware(GenericServerErrorMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)
    # Only the configured peers are trusted; uvicorn's own proxy handling is off (see the server command).
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=config.server.trusted_proxies)

    return app
