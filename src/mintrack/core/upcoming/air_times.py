import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import ENDED_STATUSES
from mintrack.db.models import Episode, Media, MediaType, TrackingStatus, UserMedia
from mintrack.integrations.tvmaze.client import TvmazeClient
from mintrack.worker.defer import defer_air_times_refresh

FOLLOWED_STATUSES = (
    TrackingStatus.NOT_STARTED,
    TrackingStatus.WATCH_LATER,
    TrackingStatus.WATCHING,
    TrackingStatus.UP_TO_DATE,
)
# Keeps a refresh of many shows under TVmaze's rate limit.
SECONDS_BETWEEN_SHOWS = 1


async def defer_air_times_refreshes(session: AsyncSession) -> int:
    """Defer a refresh of the exact air times of each followed show still airing, one show a second; returns how
    many. Each show's job holds the show's lock and is retried on its own."""
    followed = sa.exists().where(UserMedia.media_id == Media.id, UserMedia.status.in_(FOLLOWED_STATUSES))
    shows = await session.scalars(
        sa.select(Media.id)
        .where(
            Media.media_type == MediaType.TV,
            Media.tvdb_id.is_not(None),
            sa.or_(Media.tmdb_status.is_(None), Media.tmdb_status.not_in(ENDED_STATUSES)),
            followed,
        )
        .order_by(Media.id)
    )
    media_ids: list[uuid.UUID] = list(shows)
    for index, media_id in enumerate(media_ids):
        await defer_air_times_refresh(session, media_id, after=dt.timedelta(seconds=index * SECONDS_BETWEEN_SHOWS))
    return len(media_ids)


async def refresh_show_air_times(session: AsyncSession, client: TvmazeClient, show: Media) -> None:
    """Set each episode's airstamp from TVmaze, matched by season and episode number.

    Episodes TVmaze does not list, or lists without a time, lose their airstamp, so the TMDB air date applies. A show
    TVmaze does not know keeps what it has.
    """
    tvmaze_id = show.tvmaze_id
    if tvmaze_id is None and show.tvdb_id is not None:
        tvmaze_id = await client.lookup_show(show.tvdb_id)
    if tvmaze_id is None:
        return
    airstamps = {
        (episode.season, episode.number): episode.exact_airstamp
        for episode in await client.episodes(tvmaze_id)
        if episode.number is not None
    }

    show.tvmaze_id = tvmaze_id
    for episode in await session.scalars(sa.select(Episode).where(Episode.media_id == show.id)):
        episode.airstamp = airstamps.get((episode.season_number, episode.episode_number))
    await session.commit()
