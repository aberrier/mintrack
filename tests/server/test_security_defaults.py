import fastapi
import fastapi.responses
import httpx

from mintrack.config import Environment, ProjectConfig, get_config
from mintrack.server.api.asgi import build_app
from mintrack.server.common.security_headers import CONTENT_SECURITY_POLICY, SECURITY_HEADERS
from tests.server.conftest import make_client


def app_for(environment: Environment) -> fastapi.FastAPI:
    config = get_config()
    project = ProjectConfig(environment=environment, public_url=config.project.public_url)
    return build_app(config.model_copy(update={"project": project}))


async def test_every_response_carries_the_security_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert {name: response.headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS
    assert "content-security-policy" not in response.headers
    assert "server" not in response.headers


async def test_html_pages_carry_the_content_security_policy(app: fastapi.FastAPI, client: httpx.AsyncClient) -> None:
    app.add_api_route("/shows/42", lambda: fastapi.responses.HTMLResponse("<!doctype html>"))

    response = await client.get("/shows/42")

    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def test_unknown_api_paths_get_a_json_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Not Found"}


async def test_no_cross_origin_access(client: httpx.AsyncClient) -> None:
    origin = {"Origin": "https://evil.example"}

    simple = await client.get("/api/does-not-exist", headers=origin)
    preflight = await client.options("/api/health", headers={**origin, "Access-Control-Request-Method": "POST"})

    for response in (simple, preflight):
        assert not any(name.startswith("access-control-allow") for name in response.headers)


async def test_api_docs_are_served_outside_prod_only() -> None:
    async with make_client(app_for(Environment.DEV)) as dev, make_client(app_for(Environment.PROD)) as prod:
        assert (await dev.get("/api/docs")).status_code == fastapi.status.HTTP_200_OK
        assert (await dev.get("/api/openapi.json")).status_code == fastapi.status.HTTP_200_OK
        assert (await prod.get("/api/docs")).status_code == fastapi.status.HTTP_404_NOT_FOUND
        assert (await prod.get("/api/openapi.json")).status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_unhandled_errors_do_not_leak_details(app: fastapi.FastAPI, client: httpx.AsyncClient) -> None:
    def fail() -> None:
        msg = "internal detail with a secret"
        raise RuntimeError(msg)

    app.add_api_route("/api/fail", fail)

    response = await client.get("/api/fail")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["x-content-type-options"] == "nosniff"
