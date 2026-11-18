import collections.abc
import contextlib
import datetime as dt
import typing
import uuid
import zoneinfo

import pydantic
import sqlalchemy as sa
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager, episode_code
from mintrack.core.tracking.managers import (
    FutureWatchError,
    ShowTrackingChoice,
    TrackingManager,
    UnairedEpisodesError,
)
from mintrack.core.upcoming.managers import UpcomingManager, WatchListSection
from mintrack.db.database import get_database
from mintrack.db.models import Episode, Media, MediaType, TrackingStatus, User
from mintrack.integrations.tmdb.client import TMDBError, TMDBNotFoundError, get_tmdb_client

TmdbIdArgument = typing.Annotated[
    int, pydantic.Field(description="The TMDB id of the show or movie, from search_media.", ge=1)
]
SeasonArgument = typing.Annotated[int, pydantic.Field(description="The season number; 0 holds the specials.", ge=0)]
EpisodeArgument = typing.Annotated[int, pydantic.Field(description="The episode number in its season.", ge=0)]
WatchedAtArgument = typing.Annotated[
    dt.datetime | None,
    pydantic.Field(
        description="When it was watched, an ISO 8601 date-time read in the user's time zone without an offset; "
        "defaults to now."
    ),
]


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


class SeasonProgress(Schema):
    season_number: int
    # Episodes of the season, aired ones, and watched ones.
    episodes: int
    aired: int
    watched: int


class ShowProgress(Schema):
    tmdb_id: int
    title: str
    status: TrackingStatus | None
    # Every season in summary; the episodes of the season asked for, if any.
    seasons: list[SeasonProgress]
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


class WatchListEpisode(UpcomingEpisode):
    # Aired regular episodes after this one that the user has not watched.
    remaining: int
    last_watched_at: dt.datetime | None
    # "next" when watched within DORMANT_AFTER, "dormant" when not since, "not_started" when nothing was watched.
    section: WatchListSection


class UpcomingDay(Schema):
    day: dt.date
    episodes: list[UpcomingEpisode]


class Upcoming(Schema):
    days: list[UpcomingDay]


@contextlib.asynccontextmanager
async def user_session() -> collections.abc.AsyncGenerator[tuple[AsyncSession, User]]:
    """A session and the token's user; the work is committed when the tool succeeds."""
    access_token = get_access_token()
    async with get_database().session() as session:
        user = None
        if access_token is not None and access_token.subject is not None:
            user = await session.get(User, uuid.UUID(access_token.subject))
        if user is None or not user.is_active:
            msg = "Not authenticated"
            raise ToolError(msg)
        try:
            yield session, user
        except FutureWatchError:
            msg = "watched_at is in the future"
            raise ToolError(msg) from None
        except UnairedEpisodesError:
            msg = "This episode has not aired yet"
            raise ToolError(msg) from None
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


def watched_at(user: User, at: dt.datetime | None, now: dt.datetime) -> dt.datetime:
    """`at`, read in the user's time zone without an offset, or now."""
    if at is None:
        return now
    return at if at.tzinfo else at.replace(tzinfo=zoneinfo.ZoneInfo(user.timezone))


async def search_media(
    query: typing.Annotated[str, pydantic.Field(description="A title, or part of one.", min_length=1, max_length=200)],
) -> list[SearchResult]:
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


async def get_show_progress(
    tmdb_id: TmdbIdArgument,
    season_number: typing.Annotated[
        int | None, pydantic.Field(description="A season whose episodes to list; 0 holds the specials.", ge=0)
    ] = None,
) -> ShowProgress:
    """A TV show's status for the user and, per season, how many episodes aired and how many the user watched.

    With season_number, also that season's episodes, with when the user watched each one.
    """
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.TV, tmdb_id)
        manager = TrackingManager(session)
        tracking = await manager.show_tracking(user, media)
        seasons = await manager.seasons(user, media, dt.datetime.now(dt.UTC))
        episodes = await session.scalars(
            sa.select(Episode)
            .where(Episode.media_id == media.id, Episode.season_number == season_number)
            .order_by(Episode.episode_number)
        )
    if season_number is not None and season_number not in {season.season_number for season in seasons}:
        msg = f"{media.title} has no season {season_number}"
        raise ToolError(msg)
    watched = tracking.watched if tracking else {}
    return ShowProgress(
        tmdb_id=media.tmdb_id,
        title=media.title,
        status=tracking.status if tracking else None,
        seasons=[
            SeasonProgress(
                season_number=season.season_number,
                episodes=season.episode_count,
                aired=season.aired_count,
                watched=season.watched_count,
            )
            for season in seasons
        ],
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
        episode_id = await session.scalar(
            sa.select(Episode.id).where(
                Episode.media_id == media.id,
                Episode.season_number == season_number,
                Episode.episode_number == episode_number,
            )
        )
        if episode_id is None:
            msg = f"{media.title} has no episode {episode_code(season_number, episode_number)}"
            raise ToolError(msg)
        manager, now = TrackingManager(session), dt.datetime.now(dt.UTC)
        if watched:
            tracking = await manager.mark_episodes(user, media, [episode_id], watched_at(user, at, now), now=now)
        else:
            tracking = await manager.unmark_episodes(user, media, [episode_id], now)
    return ShowStatus(title=media.title, status=tracking.status if tracking else None)


async def mark_episode_watched(
    tmdb_id: TmdbIdArgument,
    season_number: SeasonArgument,
    episode_number: EpisodeArgument,
    watched_at: WatchedAtArgument = None,
) -> ShowStatus:
    """Mark one episode of a TV show watched; returns the show's resulting status. An episode that has not aired
    yet, or a watched_at in the future, is refused."""
    return await set_episode_watched(tmdb_id, season_number, episode_number, watched_at, watched=True)


async def unmark_episode_watched(
    tmdb_id: TmdbIdArgument, season_number: SeasonArgument, episode_number: EpisodeArgument
) -> ShowStatus:
    """Remove the user's watch of one episode of a TV show; returns the show's resulting status."""
    return await set_episode_watched(tmdb_id, season_number, episode_number, None, watched=False)


async def set_movie_watched(tmdb_id: int, at: dt.datetime | None, *, watched: bool) -> MovieStatus:
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.MOVIE, tmdb_id)
        now = dt.datetime.now(dt.UTC)
        tracking = await TrackingManager(session).set_movie_watched(
            user, media, watched=watched, at=watched_at(user, at, now), now=now
        )
    return MovieStatus(title=media.title, status=tracking.status, watched_at=tracking.watched_at)


async def mark_movie_watched(tmdb_id: TmdbIdArgument, watched_at: WatchedAtArgument = None) -> MovieStatus:
    """Mark a movie watched; a watched_at in the future is refused."""
    return await set_movie_watched(tmdb_id, watched_at, watched=True)


async def unmark_movie_watched(tmdb_id: TmdbIdArgument) -> MovieStatus:
    """Remove the user's watch of a movie; the movie stays in their library, to watch later."""
    return await set_movie_watched(tmdb_id, None, watched=False)


async def set_show_status(
    tmdb_id: TmdbIdArgument,
    status: typing.Annotated[
        ShowTrackingChoice, pydantic.Field(description="watching resumes the show; stopped stops following it.")
    ],
) -> ShowStatus:
    """Follow a TV show (watching), stop following it, put it aside to watch later, or resume it; MinTrack derives
    the other statuses from the episodes watched: not_started while none is, then watching, up_to_date or finished.
    Marking an episode resumes a show put aside or stopped."""
    async with user_session() as (session, user):
        media = await get_media(session, MediaType.TV, tmdb_id)
        tracking = await TrackingManager(session).set_show_status(user, media, status, dt.datetime.now(dt.UTC))
    return ShowStatus(title=media.title, status=tracking.status)


async def list_upcoming() -> Upcoming:
    """The user's episodes not watched yet airing from today over the coming weeks, grouped by day in their time
    zone; airstamp is UTC when the exact time is known. Aired episodes left to watch are in list_up_next."""
    async with user_session() as (session, user):
        upcoming = await UpcomingManager(session).upcoming(user, now=dt.datetime.now(dt.UTC))
    return Upcoming.model_validate(upcoming)


async def list_up_next() -> list[WatchListEpisode]:
    """The user's watch list: the next episode to watch of each show they follow, the first one of a show not
    started; in the sections next, dormant and not_started, most recently watched first."""
    async with user_session() as (session, user):
        episodes = await UpcomingManager(session).watch_list(user, now=dt.datetime.now(dt.UTC))
    return [WatchListEpisode.model_validate(episode) for episode in episodes]
