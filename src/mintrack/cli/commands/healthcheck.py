import http
import http.client
import urllib.request

import typer

from mintrack.config import get_config

command = typer.Typer(invoke_without_command=True, help="Exit 0 when the local server reports healthy.")

TIMEOUT_SECONDS = 5


def is_healthy(url: str, *, timeout: float = TIMEOUT_SECONDS) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status == http.HTTPStatus.OK
    except OSError, http.client.HTTPException:
        return False


@command.callback()
def main() -> None:
    server = get_config().server
    host = "127.0.0.1" if server.host in {"0.0.0.0", "::"} else server.host  # noqa: S104
    if not is_healthy(f"http://{host}:{server.port}/api/health"):
        raise typer.Exit(code=1)
