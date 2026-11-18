import fastapi
import httpx
import pytest

from tests.server.api.conftest import PASSWORD, CreateUser, log_in, xsrf

TIMEZONE = {"timezone": "Europe/Paris"}


async def test_unsafe_requests_need_the_xsrf_header(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    await log_in(api)

    missing = await api.patch("/api/auth/me", json=TIMEZONE)
    wrong = await api.patch("/api/auth/me", json=TIMEZONE, headers={"X-XSRF-TOKEN": "forged"})
    right = await api.patch("/api/auth/me", json=TIMEZONE, headers=xsrf(api))

    assert missing.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert wrong.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert right.status_code == fastapi.status.HTTP_200_OK


async def test_reading_the_user_restores_a_missing_xsrf_cookie(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    await log_in(api)
    api.cookies.delete("XSRF-TOKEN")

    await api.get("/api/auth/me")

    assert (await api.patch("/api/auth/me", json=TIMEZONE, headers=xsrf(api))).status_code == 200


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/password-link", "/api/auth/password-link/use"])
@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"]
)
async def test_public_endpoints_refuse_what_a_cross_site_form_can_send(
    api: httpx.AsyncClient, create_user: CreateUser, path: str, content_type: str
) -> None:
    await create_user("alice")
    body = f'{{"username": "alice", "password": "{PASSWORD}", "token": "t"}}'

    response = await api.post(path, content=body, headers={"Content-Type": content_type})

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "XSRF-TOKEN" not in api.cookies
