"""Deferring jobs by task name, so the managers defer them without importing the tasks, which import the managers."""

import datetime as dt
import enum
import typing
import uuid

import procrastinate
import psycopg
from procrastinate.exceptions import AlreadyEnqueued
from procrastinate.manager import JobManager
from procrastinate.tasks import configure_task
from procrastinate.types import JSONValue
from sqlalchemy.ext.asyncio import AsyncSession

# The namespace the worker app registers the tasks under.
NAMESPACE = "mintrack"


class TaskName(enum.StrEnum):
    REFRESH_MEDIA = "refresh_media"
    REFRESH_SHOW_AIR_TIMES = "refresh_show_air_times"
    SYNC_JELLYFIN_ACCOUNT = "jellyfin.sync_account"
    RUN_IMPORT = "imports.run"


# Jobs are written on the caller's connection, never through this connector, which stays closed.
_jobs = JobManager(procrastinate.PsycopgConnector())


async def defer_refresh(session: AsyncSession, media_id: uuid.UUID) -> None:
    """Defer a refresh in the session's transaction: it runs only if the transaction commits, at most once queued."""
    await _defer_for_media(session, TaskName.REFRESH_MEDIA, media_id)


async def defer_air_times_refresh(
    session: AsyncSession, media_id: uuid.UUID, *, after: dt.timedelta = dt.timedelta()
) -> None:
    """Defer a refresh of the show's air times, like `defer_refresh`, to run `after` from now."""
    await _defer_for_media(session, TaskName.REFRESH_SHOW_AIR_TIMES, media_id, after=after)


async def defer_jellyfin_sync(
    session: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID, *, full: bool = False
) -> None:
    """Defer a sync of the account like `defer_refresh`; one user's syncs and imports run one at a time."""
    kind = "full" if full else "new"
    await _defer(
        session,
        TaskName.SYNC_JELLYFIN_ACCOUNT,
        f"jellyfin_sync:{account_id}:{kind}",
        _user_tracking_lock(user_id),
        account_id=str(account_id),
        full=full,
    )


async def defer_import(session: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Defer the import job like `defer_refresh`, after the user's running syncs and imports."""
    await _defer(session, TaskName.RUN_IMPORT, f"import:{job_id}", _user_tracking_lock(user_id), job_id=str(job_id))


def _user_tracking_lock(user_id: uuid.UUID) -> str:
    # Jellyfin syncs and imports may mark the same episodes of the same user.
    return f"user_tracking:{user_id}"


async def _defer_for_media(
    session: AsyncSession, task: TaskName, media_id: uuid.UUID, *, after: dt.timedelta = dt.timedelta()
) -> None:
    # One job per media at a time: refreshes and air times both write its episodes.
    await _defer(session, task, f"{task}:{media_id}", f"media:{media_id}", after=after, media_id=str(media_id))


async def _defer(
    session: AsyncSession,
    task: TaskName,
    queueing_lock: str,
    lock: str,
    *,
    after: dt.timedelta = dt.timedelta(),
    **arguments: JSONValue,
) -> None:
    raw = await (await session.connection()).get_raw_connection()
    connection = typing.cast("psycopg.AsyncConnection", raw.driver_connection)
    deferrer = configure_task(
        name=f"{NAMESPACE}:{task}",
        job_manager=_jobs,
        connection=connection,
        queueing_lock=queueing_lock,
        lock=lock,
        task_kwargs=arguments,
        schedule_in={"seconds": int(after.total_seconds())} if after else None,
    )
    try:
        # A savepoint: the queueing lock's unique violation must not abort the transaction.
        async with connection.transaction():
            await deferrer.defer_async()
    except AlreadyEnqueued:
        pass
