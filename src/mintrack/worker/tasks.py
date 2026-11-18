import datetime as dt
import typing
import uuid

import procrastinate
import psycopg
from procrastinate import builtin_tasks
from procrastinate.exceptions import AlreadyEnqueued
from procrastinate.tasks import Task
from sqlalchemy.ext.asyncio import AsyncSession

import mintrack.worker
from mintrack.core.catalog.managers import CatalogManager, is_airing
from mintrack.core.tracking.managers import TrackingManager
from mintrack.core.upcoming.air_times import refresh_air_times, refresh_show_air_times
from mintrack.db.database import get_database
from mintrack.db.models import Media
from mintrack.integrations.tmdb.client import TMDBNotFoundError, get_tmdb_client
from mintrack.integrations.tvmaze import tvmaze_client
from mintrack.observability.logging import logger

blueprint = procrastinate.Blueprint()

FINISHED_JOBS_MAX_HOURS = 7 * 24


@blueprint.task(retry=procrastinate.RetryStrategy(max_attempts=3, exponential_wait=60))
async def refresh_media(media_id: str) -> None:
    """Refresh a movie or show from TMDB and the statuses of the users tracking it."""
    tmdb = get_tmdb_client()
    async with get_database().session() as session:
        media = await session.get(Media, uuid.UUID(media_id))
        if media is None:
            return
        media_type, tmdb_id = media.media_type, media.tmdb_id
        await session.commit()
        now = dt.datetime.now(dt.UTC)
        try:
            media = await CatalogManager(session, tmdb).fetch(media_type, tmdb_id, now)
        except TMDBNotFoundError:
            logger.warning("refresh: TMDB no longer lists this media", media_type=str(media_type), tmdb_id=tmdb_id)
            return
        await TrackingManager(session).refresh_statuses(media, now)
        await session.commit()


@blueprint.periodic(cron="17 * * * *")
@blueprint.task(queueing_lock="refresh_stale_media")
async def refresh_stale_media(timestamp: int) -> None:  # noqa: ARG001
    """Defer a refresh of every tracked media past its refresh period."""
    tmdb = get_tmdb_client()
    if not tmdb.configured:
        return
    async with get_database().session() as session:
        for media_id in await CatalogManager(session, tmdb).stale_tracked(dt.datetime.now(dt.UTC)):
            await defer_refresh(session, media_id)
        await session.commit()


@blueprint.periodic(cron="43 4 * * *")
@blueprint.task(pass_context=True, queueing_lock="remove_old_jobs")
async def remove_old_jobs(context: procrastinate.JobContext, timestamp: int) -> None:  # noqa: ARG001
    await builtin_tasks.remove_old_jobs(context, max_hours=FINISHED_JOBS_MAX_HOURS, remove_failed=True)


@blueprint.periodic(cron="0 4 * * *")
@blueprint.task(name="refresh_air_times", queueing_lock="refresh_air_times")
async def refresh_air_times_task(timestamp: int) -> None:  # noqa: ARG001
    async with get_database().session() as session, tvmaze_client() as client:
        await refresh_air_times(session, client)


@blueprint.task(name="refresh_show_air_times", retry=procrastinate.RetryStrategy(max_attempts=3, exponential_wait=60))
async def refresh_show_air_times_task(media_id: str) -> None:
    """Refresh the exact air times of a show still airing."""
    async with get_database().session() as session, tvmaze_client() as client:
        show = await session.get(Media, uuid.UUID(media_id))
        if show is not None and is_airing(show):
            await refresh_show_air_times(session, client, show)


async def defer_refresh(session: AsyncSession, media_id: uuid.UUID) -> None:
    """Defer a refresh in the session's transaction: it runs only if the transaction commits, at most once queued."""
    await _defer_for_media(session, refresh_media, f"refresh_media:{media_id}", media_id)


async def defer_air_times_refresh(session: AsyncSession, media_id: uuid.UUID) -> None:
    """Defer a refresh of the show's air times, like `defer_refresh`."""
    await _defer_for_media(session, refresh_show_air_times_task, f"refresh_show_air_times:{media_id}", media_id)


async def _defer_for_media(session: AsyncSession, task: Task, queueing_lock: str, media_id: uuid.UUID) -> None:
    # Binds the tasks to the app, whose import imports this module.
    mintrack.worker.get_worker_app()
    raw = await (await session.connection()).get_raw_connection()
    connection = typing.cast("psycopg.AsyncConnection", raw.driver_connection)
    # One job per media at a time: refreshes and air times both write its episodes.
    deferrer = task.configure(connection=connection, queueing_lock=queueing_lock, lock=f"media:{media_id}")
    try:
        # A savepoint: the queueing lock's unique violation must not abort the transaction.
        async with connection.transaction():
            await deferrer.defer_async(media_id=str(media_id))
    except AlreadyEnqueued:
        pass
