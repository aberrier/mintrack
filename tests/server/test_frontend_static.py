import collections.abc
import pathlib

import fastapi
import httpx
import pytest

from mintrack.config import ServerConfig, get_config
from mintrack.server.api.asgi import build_app
from mintrack.server.common.frontend import IMMUTABLE, REVALIDATE
from tests.server.conftest import make_client

INDEX = "<!doctype html><title>MinTrack</title>"


@pytest.fixture
def dist(tmp_path: pathlib.Path) -> pathlib.Path:
    """A built app as Angular writes it, plus files that must never be served."""
    root = tmp_path / "browser"
    (root / "icons").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "main-72OG7TZP.js").write_text("console.log('app')", encoding="utf-8")
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (root / "icons" / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (root / ".env").write_text("MINTRACK__SECURITY__SECRET_KEY=leak", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the app", encoding="utf-8")
    return root


@pytest.fixture
async def client(dist: pathlib.Path) -> collections.abc.AsyncGenerator[httpx.AsyncClient]:
    config = get_config()
    app = build_app(config.model_copy(update={"server": ServerConfig(frontend_dist=dist)}))
    async with make_client(app) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/shows/42", "/settings/profile"])
async def test_client_routes_get_the_app(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.text == INDEX
    assert response.headers["cache-control"] == REVALIDATE
    assert "content-security-policy" in response.headers


@pytest.mark.parametrize(
    ("path", "cache_control"),
    [
        ("/main-72OG7TZP.js", IMMUTABLE),
        ("/manifest.webmanifest", REVALIDATE),
        ("/icons/icon.svg", REVALIDATE),
        ("/index.html", REVALIDATE),
    ],
)
async def test_files_are_cached_only_when_their_name_is_hashed(
    client: httpx.AsyncClient, path: str, cache_control: str
) -> None:
    response = await client.get(path)

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.headers["cache-control"] == cache_control


@pytest.mark.parametrize(
    "path",
    [
        "/main-DELETED1.js",  # a stale tab asking for a chunk the new build removed
        "/.env",
        "/icons/.env",
        "/../secret.txt",
        "/%2e%2e/secret.txt",
        "/icons/..%2f..%2fsecret.txt",
    ],
)
async def test_missing_hidden_and_outside_files_are_not_found(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert "leak" not in response.text
    assert "outside the app" not in response.text
    assert response.text != INDEX


@pytest.mark.parametrize("path", ["/api/unknown", "/api", "/mcp/tools", "/.well-known/security.txt"])
async def test_reserved_backend_paths_never_fall_back_to_the_app(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Not Found"}


async def test_api_routes_still_win_over_the_app(client: httpx.AsyncClient, database: object) -> None:
    response = await client.get("/api/health")

    assert response.json()["status"] == "ok"


async def test_only_reads_reach_the_app(client: httpx.AsyncClient) -> None:
    response = await client.post("/shows/42")

    assert response.status_code == fastapi.status.HTTP_405_METHOD_NOT_ALLOWED


async def test_a_wrong_method_on_an_api_route_keeps_its_405(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/health")

    assert response.status_code == fastapi.status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET"


async def test_unknown_api_paths_get_a_json_404_whatever_the_method(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/unknown")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Not Found"}


async def test_a_null_byte_does_not_break_the_server(client: httpx.AsyncClient) -> None:
    response = await client.get("/%00")

    # No extension, so it is a client route: the app answers (and its router shows its own page).
    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.text == INDEX
