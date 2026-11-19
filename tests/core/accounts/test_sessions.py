import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.devices import USER_AGENT_MAX_LENGTH
from mintrack.core.accounts.managers import SESSION_IDLE_TIMEOUT, AccountManager
from mintrack.db.models import PushSubscription, User, UserSession

NOW = dt.datetime(2026, 11, 18, tzinfo=dt.UTC)


async def test_sessions_unused_past_the_idle_timeout_are_deleted_with_their_devices(
    db_session: AsyncSession, user: User
) -> None:
    manager = AccountManager(db_session)
    expired_at, recent_at = NOW - SESSION_IDLE_TIMEOUT - dt.timedelta(minutes=1), NOW - dt.timedelta(days=1)
    for last_used_at in (expired_at, recent_at):
        await manager.create_session(user, now=last_used_at)
        db_session.add(
            PushSubscription(
                user_id=user.id,
                session_id=await db_session.scalar(sa.select(UserSession.id).filter_by(last_used_at=last_used_at)),
                endpoint=f"https://push.test/{last_used_at.isoformat()}",
                p256dh="k",
                auth="a",
                created_at=last_used_at,
            )
        )
    await db_session.flush()

    assert await manager.delete_expired_sessions(NOW) == 1

    remaining = await db_session.scalars(sa.select(UserSession.last_used_at).filter_by(user_id=user.id))
    assert list(remaining) == [recent_at]
    devices = await db_session.scalars(sa.select(PushSubscription.created_at).filter_by(user_id=user.id))
    assert list(devices) == [recent_at]


async def test_a_session_keeps_a_bounded_user_agent(db_session: AsyncSession, user: User) -> None:
    await AccountManager(db_session).create_session(user, now=NOW, user_agent="x" * 2000)

    stored = await db_session.scalar(sa.select(UserSession.user_agent).filter_by(user_id=user.id))
    assert stored == "x" * USER_AGENT_MAX_LENGTH
