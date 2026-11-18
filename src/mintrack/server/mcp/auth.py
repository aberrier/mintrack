import datetime as dt

from mcp.server.auth.provider import AccessToken

from mintrack.core.api_tokens.managers import ApiTokenManager
from mintrack.db.database import get_database


class ApiTokenVerifier:
    """Accept a user's API token as the MCP Bearer token; the access token's subject is the user id."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with get_database().session() as session:
            found = await ApiTokenManager(session).authenticate(token, dt.datetime.now(dt.UTC))
            if found is None:
                return None
            api_token, user = found
            await session.commit()
            return AccessToken(token=token, client_id=str(api_token.id), subject=str(user.id), scopes=[])
