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
    if migrate:
        alembic.upgrade(config.database.url())
    uvicorn.run(**uvicorn_options(config, reload=reload))
