import fastapi
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.database import DatabaseManager
from mintrack.db.models import ApiToken, User
from tests.server.conftest import make_client
from tests.server.mcp.conftest import TokenUser

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


async def post_initialize(app: fastapi.FastAPI, headers: dict[str, str]) -> httpx.Response:
    async with make_client(app) as client:
        return await client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS | headers)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer mt_unknown"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Cookie": "mintrack_session=anything"},
    ],
    ids=["no header", "unknown token", "basic", "cookie"],
)
async def test_requests_without_a_valid_token_get_401(mcp_app: fastapi.FastAPI, headers: dict[str, str]) -> None:
    response = await post_initialize(mcp_app, headers)

    assert response.status_code == fastapi.status.HTTP_401_UNAUTHORIZED
    assert response.headers["www-authenticate"].startswith("Bearer ")


async def test_a_valid_token_initializes_and_records_its_use(
    mcp_app: fastapi.FastAPI, token_user: TokenUser, database: DatabaseManager
) -> None:
    response = await post_initialize(mcp_app, {"Authorization": f"Bearer {token_user.token}"})

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json()["result"]["serverInfo"]["name"] == "MinTrack"
    async with AsyncSession(database.engine) as session:
        last_used_at = await session.scalar(
            sa.select(ApiToken.last_used_at).where(ApiToken.user_id == token_user.user.id)
        )
    assert last_used_at is not None


async def test_a_revoked_token_is_refused_on_the_next_request(
    mcp_app: fastapi.FastAPI, token_user: TokenUser, database: DatabaseManager
) -> None:
    headers = {"Authorization": f"Bearer {token_user.token}"}
    assert (await post_initialize(mcp_app, headers)).status_code == fastapi.status.HTTP_200_OK
    async with AsyncSession(database.engine) as session:
        await session.execute(sa.delete(ApiToken).where(ApiToken.user_id == token_user.user.id))
        await session.commit()

    response = await post_initialize(mcp_app, headers)

    assert response.status_code == fastapi.status.HTTP_401_UNAUTHORIZED


async def test_a_disabled_users_token_is_refused(
    mcp_app: fastapi.FastAPI, token_user: TokenUser, database: DatabaseManager
) -> None:
    async with AsyncSession(database.engine) as session:
        await session.execute(sa.update(User).where(User.id == token_user.user.id).values(is_active=False))
        await session.commit()

    response = await post_initialize(mcp_app, {"Authorization": f"Bearer {token_user.token}"})

    assert response.status_code == fastapi.status.HTTP_401_UNAUTHORIZED
