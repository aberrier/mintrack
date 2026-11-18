import fastapi
import pytest

from mintrack.config import ServerConfig, get_config
from mintrack.server.api.asgi import build_app
from tests.server.conftest import make_client

FORWARDED = {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"}


def app_trusting(forwarded_allow_ips: str) -> fastapi.FastAPI:
    config = get_config()
    server = ServerConfig(forwarded_allow_ips=forwarded_allow_ips)
    app = build_app(config.model_copy(update={"server": server}))

    @app.get("/api/test/client")
    def client_info(request: fastapi.Request) -> dict[str, str | None]:
        return {"host": request.client.host if request.client else None, "scheme": request.url.scheme}

    return app


@pytest.mark.parametrize("peer", ["10.1.2.3", "172.30.0.1"])
async def test_trusted_peers_set_client_address_and_scheme(peer: str) -> None:
    async with make_client(app_trusting("10.0.0.0/8,172.30.0.1"), peer=peer) as client:
        response = await client.get("http://mintrack.test/api/test/client", headers=FORWARDED)

    assert response.json() == {"host": "203.0.113.7", "scheme": "https"}


@pytest.mark.parametrize(
    ("forwarded_allow_ips", "peer"),
    [
        ("10.0.0.0/8", "192.0.2.10"),
        # Nothing is trusted by default, not even 127.0.0.1.
        ("", "127.0.0.1"),
    ],
)
async def test_other_peers_cannot_forge_forwarded_headers(forwarded_allow_ips: str, peer: str) -> None:
    async with make_client(app_trusting(forwarded_allow_ips), peer=peer) as client:
        response = await client.get("http://mintrack.test/api/test/client", headers=FORWARDED)

    assert response.json() == {"host": peer, "scheme": "http"}
