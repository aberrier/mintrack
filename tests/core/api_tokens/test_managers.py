import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.api_tokens.managers import ApiTokenManager
from mintrack.db.models import User

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.UTC)


async def test_authenticate_returns_the_token_and_its_user(db_session: AsyncSession, user: User) -> None:
    manager = ApiTokenManager(db_session)
    token, raw_token = await manager.create(user, "Claude", NOW)

    assert await manager.authenticate(raw_token, NOW) == (token, user)


async def test_authenticate_refuses_unknown_tokens_and_disabled_users(db_session: AsyncSession, user: User) -> None:
    manager = ApiTokenManager(db_session)
    _, raw_token = await manager.create(user, "Claude", NOW)

    assert await manager.authenticate(raw_token + "x", NOW) is None
    user.is_active = False
    await db_session.flush()
    assert await manager.authenticate(raw_token, NOW) is None


@pytest.mark.parametrize(
    ("last_used_at", "expected"),
    [
        (None, NOW),
        (NOW - dt.timedelta(minutes=5), NOW),
        (NOW - dt.timedelta(minutes=4), NOW - dt.timedelta(minutes=4)),
    ],
)
async def test_authenticate_writes_last_used_at_at_most_every_five_minutes(
    db_session: AsyncSession, user: User, last_used_at: dt.datetime | None, expected: dt.datetime
) -> None:
    manager = ApiTokenManager(db_session)
    token, raw_token = await manager.create(user, "Claude", NOW - dt.timedelta(days=1))
    token.last_used_at = last_used_at

    await manager.authenticate(raw_token, NOW)

    assert token.last_used_at == expected
