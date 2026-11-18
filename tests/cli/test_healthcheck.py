import collections.abc
import http
import http.server
import threading

import pytest

from mintrack.cli.commands.healthcheck import is_healthy


@pytest.fixture
def server_answering() -> collections.abc.Generator[collections.abc.Callable[[http.HTTPStatus], str]]:
    servers: list[http.server.HTTPServer] = []

    def start(status: http.HTTPStatus) -> str:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(status)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{httpd.server_port}/api/health"

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def test_healthy_only_on_200(server_answering: collections.abc.Callable[[http.HTTPStatus], str]) -> None:
    assert is_healthy(server_answering(http.HTTPStatus.OK)) is True
    assert is_healthy(server_answering(http.HTTPStatus.SERVICE_UNAVAILABLE)) is False


def test_unhealthy_when_nothing_listens() -> None:
    assert is_healthy("http://127.0.0.1:1/api/health", timeout=1) is False
