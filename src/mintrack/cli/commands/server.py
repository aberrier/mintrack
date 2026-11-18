import typing

import typer
import uvicorn

from mintrack.config import Config, get_config
from mintrack.db import alembic
from mintrack.observability.logging import logger, logging_config

command = typer.Typer(invoke_without_command=True, help="Run the web server.")

ASGI_APP = "mintrack.server.api.asgi:build_app"


def uvicorn_options(config: Config, *, reload: bool) -> dict[str, typing.Any]:
    return {
        "app": ASGI_APP,
        "factory": True,
        "host": config.server.host,
        "port": config.server.port,
        # Proxy headers are handled by the app's ProxyHeadersMiddleware (see build_app).
        "proxy_headers": False,
        "server_header": False,
        "log_config": logging_config(config.logging),
        "reload": reload,
    }


def proxy_setting_missing(config: Config) -> bool:
    """An https address is served through a reverse proxy, whose address must be trusted for the client's."""
    return config.project.public_url.scheme == "https" and not config.server.forwarded_allow_ips


@command.callback()
def main(
    *,
    migrate: typing.Annotated[bool, typer.Option(help="Upgrade the database schema before starting.")] = True,
    reload: typing.Annotated[bool, typer.Option(help="Restart on code changes (development).")] = False,
) -> None:
    config = get_config()
    logger.info(
        "starting MinTrack",
        version=config.project.version,
        commit=config.project.commit,
        environment=str(config.project.environment),
        public_url=config.project.public_origin,
        trusted_proxies=config.server.trusted_proxies,
    )
    if proxy_setting_missing(config):
        logger.warning(
            "an https public URL usually means a reverse proxy: set MINTRACK__SERVER__FORWARDED_ALLOW_IPS to its "
            "address, or every client shares the proxy's address (login limits included)"
        )
    if config.tmdb.api_key is None:
        logger.warning("TMDB is not configured: set MINTRACK__TMDB__API_KEY to enable search and new pages")
    if migrate:
        alembic.upgrade(config.database.url())
    uvicorn.run(**uvicorn_options(config, reload=reload))
