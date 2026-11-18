import collections.abc
import contextlib
import datetime as dt
import enum
import uuid
import zoneinfo

import pydantic
import sqlalchemy as sa
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import TrackingManager
from mintrack.core.upcoming.managers import UpcomingManager, WatchListSection
from mintrack.db.database import get_database
from mintrack.db.models import Episode, Media, MediaType, TrackingStatus, User
from mintrack.integrations.tmdb.client import TMDBError, TMDBNotFoundError, get_tmdb_client


class ShowStatusChoice(enum.StrEnum):
    WATCHING = enum.auto()
    WATCH_LATER = enum.auto()
    STOPPED = enum.auto()


class Schema(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)


class SearchResult(Schema):
    tmdb_id: int
    media_type: MediaType
    title: str
    release_date: dt.date | None
    tracking_status: TrackingStatus | None


class EpisodeProgress(Schema):
    season_number: int
    episode_number: int
    title: str
    air_date: dt.date | None
    watched_at: dt.datetime | None


class ShowProgress(Schema):
    tmdb_id: int
    title: str
    status: TrackingStatus | None
    episodes: list[EpisodeProgress]


class ShowStatus(Schema):
    title: str
    status: TrackingStatus | None


class MovieStatus(Schema):
    title: str
    status: TrackingStatus
    watched_at: dt.datetime | None


class UpcomingEpisode(Schema):
    tmdb_id: int
    show_title: str
    season_number: int
    episode_number: int
    title: str
    airstamp: dt.datetime | None
    day: dt.date | None


class UpNextEpisode(UpcomingEpisode):
    # Aired regular episodes after this one that the user has not watched.
    remaining: int
    last_watched_at: dt.datetime | None
    # "next" when watched in the last 30 days, else "dormant".
    section: WatchListSection


class UpcomingDay(Schema):
    day: dt.date
    episodes: list[UpcomingEpisode]


class Upcoming(Schema):
    new: list[UpcomingEpisode]
    days: list[UpcomingDay]


@contextlib.asynccontextmanager
async def user_session() -> collections.abc.AsyncGenerator[tuple[AsyncSession, User]]:
    """A session and the token's user; the work is committed when the tool succeeds."""
    access_token = get_access_token()
    async with AsyncSession(get_database().engine, expire_on_commit=False) as session:
        user = None
        if access_token is not None and access_token.subject is not None:
            user = await session.get(User, uuid.UUID(access_token.subject))
        if user is None or not user.is_active:
            msg = "Not authenticated"
            raise ToolError(msg)
        yield session, user
        await session.commit()


async def get_media(session: AsyncSession, media_type: MediaType, tmdb_id: int) -> Media:
    """The media from the cache, or from TMDB on its first request."""
    try:
        return await CatalogManager(session, get_tmdb_client()).get_or_fetch(
            media_type, tmdb_id, dt.datetime.now(dt.UTC)
        )
    except TMDBNotFoundError:
        msg = f"No {media_type} with TMDB id {tmdb_id}"
        raise ToolError(msg) from None
    except TMDBError as error:
        raise ToolError(str(error)) from None


async def episodes_of(session: AsyncSession, media: Media) -> collections.abc.Sequence[Episode]:
    query = (
        sa.select(Episode).where(Episode.media_id == media.id).order_by(Episode.season_number, Episode.episode_number)
    )
    return (await session.scalars(query)).all()


def in_user_timezone(user: User, at: dt.datetime | None) -> dt.datetime:
    if at is None:
        return dt.datetime.now(dt.UTC)
    return at if at.tzinfo else at.replace(tzinfo=zoneinfo.ZoneInfo(user.timezone))


async def search_media(query: str) -> list[SearchResult]:
    """Search movies and TV shows (anime included) on TMDB by title.

    Returns each result's tmdb_id and media_type, which the other tools take, and the user's status when tracked.
    """
    async with user_session() as (session, user):
        try:
            hits = await CatalogManager(session, get_tmdb_client()).search(user, query)
        except TMDBError as error:
            raise ToolError(str(error)) from None
    return [
        SearchResult(
            tmdb_id=hit.result.id,
            media_type=hit.result.media_type,
            title=hit.result.title,
            release_date=hit.result.release_date,
            tracking_status=hit.tracking_status,
        )
        for hit in hits
    ]


async def get_show_progress(tmdb_id: int) -> ShowProgress:
    """A TV show's status for the user and every episode, with when the user watched it."""
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.TV, tmdb_id)
        tracking = await TrackingManager(session).show_tracking(user, media)
        episodes = await episodes_of(session, media)
    watched = tracking.watched if tracking else {}
    return ShowProgress(
        tmdb_id=media.tmdb_id,
        title=media.title,
        status=tracking.status if tracking else None,
        episodes=[
            EpisodeProgress(
                season_number=episode.season_number,
                episode_number=episode.episode_number,
                title=episode.title,
                air_date=episode.air_date,
                watched_at=watched.get(episode.id),
            )
            for episode in episodes
        ],
    )


async def set_episode_watched(
    tmdb_id: int, season_number: int, episode_number: int, at: dt.datetime | None, *, watched: bool
) -> ShowStatus:
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.TV, tmdb_id)
        episode = await session.scalar(
            sa.select(Episode).where(
                Episode.media_id == media.id,
                Episode.season_number == season_number,
                Episode.episode_number == episode_number,
            )
        )
        if episode is None:
            msg = f"{media.title} has no episode S{season_number:02}E{episode_number:02}"
            raise ToolError(msg)
        manager = TrackingManager(session)
        if watched:
            tracking = await manager.mark_watched(user, episode, in_user_timezone(user, at))
        else:
            tracking = await manager.unmark_watched(user, episode, dt.datetime.now(dt.UTC))
    return ShowStatus(title=media.title, status=tracking.status if tracking else None)


async def mark_episode_watched(
    tmdb_id: int, season_number: int, episode_number: int, watched_at: dt.datetime | None = None
) -> ShowStatus:
    """Mark one episode of a TV show watched; returns the show's resulting status.

    watched_at is an ISO 8601 date-time, read in the user's time zone when it has no offset; it defaults to now.
    """
    return await set_episode_watched(tmdb_id, season_number, episode_number, watched_at, watched=True)


async def unmark_episode_watched(tmdb_id: int, season_number: int, episode_number: int) -> ShowStatus:
    """Remove the user's watch of one episode of a TV show; returns the show's resulting status."""
    return await set_episode_watched(tmdb_id, season_number, episode_number, None, watched=False)


async def set_movie_watched(tmdb_id: int, at: dt.datetime | None, *, watched: bool) -> MovieStatus:
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.MOVIE, tmdb_id)
        tracking = await TrackingManager(session).set_movie_watched(
            user, media, watched=watched, now=in_user_timezone(user, at)
        )
    return MovieStatus(title=media.title, status=tracking.status, watched_at=tracking.watched_at)


async def mark_movie_watched(tmdb_id: int, watched_at: dt.datetime | None = None) -> MovieStatus:
    """Mark a movie watched.

    watched_at is an ISO 8601 date-time, read in the user's time zone when it has no offset; it defaults to now.
    """
    return await set_movie_watched(tmdb_id, watched_at, watched=True)


async def unmark_movie_watched(tmdb_id: int) -> MovieStatus:
    """Remove the user's watch of a movie; the movie stays in their library, to watch later."""
    return await set_movie_watched(tmdb_id, None, watched=False)


async def set_show_status(tmdb_id: int, status: ShowStatusChoice) -> ShowStatus:
    """Stop following a TV show, put it aside to watch later, or resume it; MinTrack derives the other statuses
    from the episodes watched. Marking an episode resumes a show put aside or stopped."""
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.TV, tmdb_id)
        manager, now = TrackingManager(session), dt.datetime.now(dt.UTC)
        if status is ShowStatusChoice.WATCH_LATER:
            tracking = await manager.watch_later(user, media, now)
        else:
            tracking = await manager.track_show(user, media, stopped=status is ShowStatusChoice.STOPPED, now=now)
    return ShowStatus(title=media.title, status=tracking.status)


async def list_upcoming() -> Upcoming:
    """The user's episodes airing in the coming weeks, grouped by day in their time zone, and the new episodes
    aired since the last one they watched; airstamp is UTC when the exact time is known."""
    async with user_session() as (session, user):
        upcoming = await UpcomingManager(session).upcoming(user, now=dt.datetime.now(dt.UTC))
    return Upcoming.model_validate(upcoming)


async def list_up_next() -> list[UpNextEpisode]:
    """The next episode to watch of each show the user is watching, most recently watched first."""
    async with user_session() as (session, user):
        episodes = await UpcomingManager(session).up_next(user, now=dt.datetime.now(dt.UTC))
    return [UpNextEpisode.model_validate(episode) for episode in episodes]
