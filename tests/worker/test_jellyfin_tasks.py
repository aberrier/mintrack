import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.jellyfin.managers import JellyfinManager
from mintrack.db.models import JellyfinSyncStatus, User, WatchedMovie
from mintrack.integrations.tmdb.client import TMDBClient
from mintrack.worker import tasks
from tests.fakes.jellyfin import SERVER_URL, FakeJellyfin


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_the_periodic_job_queues_one_sync_per_account_once(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, monkeypatch: pytest.MonkeyPatch
) -> None:
    jellyfin.add_user("bob", "secret")
    jellyfin.add_user("carol", "secret")
    manager = JellyfinManager(db_session)
    bob = await manager.link(user, SERVER_URL, "bob", "secret")
    carol = await manager.link(user, SERVER_URL, "carol", "secret")

    await tasks.sync_jellyfin_accounts(timestamp=0)
    await tasks.defer_jellyfin_sync(db_session, bob.id, bob.user_id)

    queued = (
        await db_session.execute(
            sa.text(
                "SELECT args->>'account_id', lock FROM procrastinate_jobs "
                "WHERE task_name = 'mintrack:jellyfin.sync_account'"
            )
        )
    ).all()
    assert sorted(account_id for account_id, _ in queued) == sorted([str(bob.id), str(carol.id)])
    # A user's accounts never sync at the same time: they may mark the same episodes.
    assert {lock for _, lock in queued} == {f"user_tracking:{user.id}"}


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_disabled_users_and_revoked_tokens_are_not_synced(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, tmdb: TMDBClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    jellyfin.add_user("bob", "secret")
    jellyfin.add_user("carol", "secret")
    jellyfin.play_movie("bob", {"Tmdb": "603"}, dt.datetime(2026, 11, 1, tzinfo=dt.UTC))
    manager = JellyfinManager(db_session)
    revoked = await manager.link(user, SERVER_URL, "carol", "secret")
    revoked.last_sync_status = JellyfinSyncStatus.UNAUTHORIZED
    other = User(username="disabled", is_active=False)
    db_session.add(other)
    await db_session.flush()
    disabled = await manager.link(other, SERVER_URL, "bob", "secret")
    await db_session.execute(
        sa.text("DELETE FROM procrastinate_jobs WHERE task_name = 'mintrack:jellyfin.sync_account'")
    )
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: tmdb)

    await tasks.sync_jellyfin_accounts(timestamp=0)
    await tasks.sync_jellyfin_account(account_id=str(disabled.id))

    queued = await db_session.scalar(
        sa.text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'mintrack:jellyfin.sync_account'")
    )
    assert queued == 0
    assert await db_session.scalar(sa.select(sa.func.count()).where(WatchedMovie.user_id == other.id)) == 0


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_the_sync_job_syncs_the_account(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, tmdb: TMDBClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    jellyfin.add_user("bob", "secret")
    jellyfin.play_movie("bob", {"Tmdb": "603"}, dt.datetime(2026, 11, 1, tzinfo=dt.UTC))
    account = await JellyfinManager(db_session).link(user, SERVER_URL, "bob", "secret")
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: tmdb)

    await tasks.sync_jellyfin_account(account_id=str(account.id))

    await db_session.refresh(account)
    assert account.last_sync_status == JellyfinSyncStatus.OK
    assert await db_session.scalar(sa.select(sa.func.count()).where(WatchedMovie.user_id == user.id)) == 1
