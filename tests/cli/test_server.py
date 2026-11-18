from mintrack.cli.commands.server import uvicorn_options
from mintrack.config import get_config


def test_uvicorn_leaves_proxy_headers_to_the_app_and_hides_its_name() -> None:
    options = uvicorn_options(get_config(), reload=False)

    assert options["proxy_headers"] is False
    assert options["server_header"] is False
    assert (options["app"], options["factory"]) == ("mintrack.server.api.asgi:build_app", True)
    assert (options["host"], options["port"]) == ("127.0.0.1", 8000)
