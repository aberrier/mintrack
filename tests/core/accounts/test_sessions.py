import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.managers import SESSION_IDLE_TIMEOUT, AccountManager
from mintrack.db.models import User, UserSession

NOW = dt.datetime(2026, 11, 18, tzinfo=dt.UTC)


async def test_sessions_unused_past_the_idle_timeout_are_deleted(db_session: AsyncSession, user: User) -> None:
    manager = AccountManager(db_session)
    await manager.create_session(user, now=NOW - SESSION_IDLE_TIMEOUT - dt.timedelta(minutes=1))
    await manager.create_session(user, now=NOW - dt.timedelta(days=1))

    assert await manager.delete_expired_sessions(NOW) == 1

    remaining = await db_session.scalars(sa.select(UserSession.last_used_at).filter_by(user_id=user.id))
    assert list(remaining) == [NOW - dt.timedelta(days=1)]
