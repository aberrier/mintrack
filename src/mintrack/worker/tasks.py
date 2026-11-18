import datetime as dt
import uuid

import procrastinate
import sqlalchemy as sa
from procrastinate import builtin_tasks

from mintrack.core.accounts.managers import AccountManager
from mintrack.core.catalog.managers import CatalogManager, is_airing
from mintrack.core.imports.managers import ImportManager
from mintrack.core.jellyfin.managers import JellyfinManager
from mintrack.core.push.managers import PushManager
from mintrack.core.push.webpush import get_vapid_key, push_client
from mintrack.core.tracking.managers import TrackingManager
from mintrack.core.upcoming.air_times import defer_air_times_refreshes, refresh_show_air_times
from mintrack.db.database import get_database
from mintrack.db.models import JellyfinAccount, JellyfinSyncStatus, Media, User
from mintrack.integrations.tmdb.client import TMDBNotFoundError, get_tmdb_client
from mintrack.integrations.tvmaze.client import tvmaze_client
from mintrack.observability.logging import logger

from .defer import TaskName, defer_jellyfin_sync, defer_refresh

blueprint = procrastinate.Blueprint()

FINISHED_JOBS_MAX_HOURS = 7 * 24
# Calls to outside services retry after 5, then 10 minutes, without holding their locks for long.
RETRY = procrastinate.RetryStrategy(max_attempts=3, linear_wait=300)
# A job whose worker sent no heartbeat for this long (killed, out of memory) is retried.
STALLED_AFTER_SECONDS = 600


@blueprint.task(name=TaskName.REFRESH_MEDIA, retry=RETRY)
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
@blueprint.task(name="refresh_stale_media", queueing_lock="refresh_stale_media")
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
@blueprint.task(name="remove_old_jobs", pass_context=True, queueing_lock="remove_old_jobs")
async def remove_old_jobs(context: procrastinate.JobContext, timestamp: int) -> None:  # noqa: ARG001
    await builtin_tasks.remove_old_jobs(
        context, max_hours=FINISHED_JOBS_MAX_HOURS, remove_failed=True, remove_cancelled=True, remove_aborted=True
    )


@blueprint.periodic(cron="*/5 * * * *")
@blueprint.task(name="retry_stalled_jobs", pass_context=True, queueing_lock="retry_stalled_jobs")
async def retry_stalled_jobs(context: procrastinate.JobContext, timestamp: int) -> None:  # noqa: ARG001
    """Retry the jobs of workers that stopped without finishing them, which would otherwise keep their locks."""
    manager = context.app.job_manager
    for job in await manager.get_stalled_jobs(seconds_since_heartbeat=STALLED_AFTER_SECONDS):
        logger.warning("retrying a stalled job", task=job.task_name, job_id=job.id)
        await manager.retry_job(job)


@blueprint.periodic(cron="27 3 * * *")
@blueprint.task(name="delete_expired_sessions", queueing_lock="delete_expired_sessions")
async def delete_expired_sessions(timestamp: int) -> None:  # noqa: ARG001
    async with get_database().session() as session:
        await AccountManager(session).delete_expired_sessions(dt.datetime.now(dt.UTC))
        await session.commit()


@blueprint.periodic(cron="0 4 * * *")
@blueprint.task(name="refresh_air_times", queueing_lock="refresh_air_times")
async def refresh_air_times_task(timestamp: int) -> None:  # noqa: ARG001
    async with get_database().session() as session:
        await defer_air_times_refreshes(session)
        await session.commit()


@blueprint.task(name=TaskName.REFRESH_SHOW_AIR_TIMES, retry=RETRY)
async def refresh_show_air_times_task(media_id: str) -> None:
    """Refresh the exact air times of a show still airing."""
    async with get_database().session() as session, tvmaze_client() as client:
        show = await session.get(Media, uuid.UUID(media_id))
        if show is not None and is_airing(show):
            await refresh_show_air_times(session, client, show)


@blueprint.periodic(cron="*/10 * * * *")
@blueprint.task(name="notify_aired_episodes", queueing_lock="notify_aired_episodes")
async def notify_aired_episodes(timestamp: int) -> None:
    """Send push notifications for the followed episodes that just aired."""
    key = get_vapid_key()
    if key is None:
        return
    now = dt.datetime.fromtimestamp(timestamp, dt.UTC)
    async with get_database().session() as session, push_client() as client:
        count = await PushManager(session, client, key).notify_aired_episodes(now)
    if count:
        logger.info("episode notifications sent", episodes=count)


@blueprint.task(name=TaskName.SYNC_JELLYFIN_ACCOUNT)
async def sync_jellyfin_account(account_id: str, *, full: bool = False) -> None:
    async with get_database().session() as session:
        account = await session.get(JellyfinAccount, uuid.UUID(account_id))
        if account is not None and (await session.get_one(User, account.user_id)).is_active:
            await JellyfinManager(session).sync(account, get_tmdb_client(), dt.datetime.now(dt.UTC), full=full)


@blueprint.periodic(cron="*/15 * * * *")
@blueprint.task(name="jellyfin.sync_accounts", queueing_lock="jellyfin.sync_accounts")
async def sync_jellyfin_accounts(timestamp: int) -> None:  # noqa: ARG001
    """Queue a sync of the accounts of active users; a revoked token waits for the user to link the account again."""
    async with get_database().session() as session:
        accounts = await session.execute(
            sa.select(JellyfinAccount.id, JellyfinAccount.user_id)
            .join(User, User.id == JellyfinAccount.user_id)
            .where(
                User.is_active,
                JellyfinAccount.last_sync_status.is_distinct_from(JellyfinSyncStatus.UNAUTHORIZED),
            )
        )
        for account_id, user_id in accounts.all():
            await defer_jellyfin_sync(session, account_id, user_id)
        await session.commit()


@blueprint.task(name=TaskName.RUN_IMPORT)
async def run_import(job_id: str) -> None:
    async with get_database().session() as session:
        await ImportManager(session, get_tmdb_client()).run(uuid.UUID(job_id))
