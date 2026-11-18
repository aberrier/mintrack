import re
import uuid

import fastapi
import httpx

from tests.server.api.conftest import CreateUser, log_in, xsrf

PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/password-link"),
    ("POST", "/api/auth/password-link/use"),
}
ADMIN_PREFIX = "/api/admin/"


def api_routes(app: fastapi.FastAPI) -> list[tuple[str, str]]:
    """Every method and path of the API schema, with path parameters filled in."""
    return [
        (method.upper(), re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]


async def test_every_route_but_the_public_ones_needs_a_session(
    api_app: fastapi.FastAPI, api: httpx.AsyncClient
) -> None:
    routes = api_routes(api_app)
    assert set(routes) >= PUBLIC

    for method, path in routes:
        if (method, path) not in PUBLIC:
            response = await api.request(method, path)
            assert response.status_code == fastapi.status.HTTP_401_UNAUTHORIZED, (method, path)


async def test_admin_routes_are_refused_to_other_users(
    api_app: fastapi.FastAPI, api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    await create_user("alice")
    await log_in(api)
    admin_routes = [(method, path) for method, path in api_routes(api_app) if path.startswith(ADMIN_PREFIX)]
    assert admin_routes

    for method, path in admin_routes:
        response = await api.request(method, path, headers=xsrf(api), json={})
        assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN, (method, path)
