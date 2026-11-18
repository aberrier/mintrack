import collections.abc
import datetime as dt
import secrets
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.tokens import hash_token
from mintrack.db.models import ApiToken, User

# Lets secret scanners recognise a leaked token.
TOKEN_PREFIX = "mt_"  # noqa: S105
# last_used_at is written at most this often, not on every request.
LAST_USED_RESOLUTION = dt.timedelta(minutes=5)


class ApiTokenManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user: User, name: str, now: dt.datetime) -> tuple[ApiToken, str]:
        """Return the new token and its value, which is never stored."""
        raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = ApiToken(user_id=user.id, name=name, token_hash=hash_token(raw_token), created_at=now)
        self.session.add(token)
        await self.session.flush()
        return token, raw_token

    async def list_for(self, user: User) -> collections.abc.Sequence[ApiToken]:
        query = sa.select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc(), ApiToken.id)
        return (await self.session.scalars(query)).all()

    async def revoke(self, user: User, token_id: uuid.UUID) -> bool:
        query = sa.delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id).returning(ApiToken.id)
        return (await self.session.scalar(query)) is not None

    async def authenticate(self, raw_token: str, now: dt.datetime) -> tuple[ApiToken, User] | None:
        """The token and its user, when the token exists and the user is active."""
        query = (
            sa.select(ApiToken, User)
            .join(User, User.id == ApiToken.user_id)
            .where(ApiToken.token_hash == hash_token(raw_token), User.is_active)
        )
        row = (await self.session.execute(query)).one_or_none()
        if row is None:
            return None
        token, user = row
        if token.last_used_at is None or now - token.last_used_at >= LAST_USED_RESOLUTION:
            token.last_used_at = now
        return token, user
