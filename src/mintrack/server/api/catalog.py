import collections.abc
import contextlib
import datetime as dt
import typing
import uuid

import fastapi
import pydantic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager, SearchHit, find_media
from mintrack.core.tracking.managers import TrackingManager
from mintrack.core.upcoming.managers import UpcomingManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import Episode, Media, MediaType, Season, TrackingStatus
from mintrack.integrations.tmdb.client import TMDBError, TMDBNotConfiguredError, TMDBNotFoundError
from mintrack.server.api.dependencies import CurrentUserDepType, TMDBClientDepType

router = fastapi.APIRouter(tags=["catalog"])

TMDBId = typing.Annotated[int, fastapi.Path(ge=1)]
MediaTypeQuery = typing.Annotated[MediaType, fastapi.Query(alias="type")]


class SearchResult(pydantic.BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None
    poster_path: str | None
    tracking_status: TrackingStatus | None

    @classmethod
    def of(cls, hit: SearchHit) -> typing.Self:
        return cls(
            tmdb_id=hit.result.id,
            media_type=hit.result.media_type,
            title=hit.result.title,
            year=hit.result.release_date.year if hit.result.release_date else None,
            poster_path=hit.result.poster_path,
            tracking_status=hit.tracking_status,
        )


class EpisodeResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: uuid.UUID
    season_number: int
    episode_number: int
    title: str
    air_date: dt.date | None
    airstamp: dt.datetime | None


class SeasonResponse(pydantic.BaseModel):
    """A season in summary; its episodes come from the season's own endpoint."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    season_number: int
    title: str
    episode_count: int
    # Episodes the user watched.
    watched_count: int
    # Aired episodes, and watched ones not aired as far as their date says.
    aired_count: int


class SeasonEpisodesResponse(pydantic.BaseModel):
    season_number: int
    title: str
    episodes: list[EpisodeResponse]


class ShowTrackingResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    status: TrackingStatus
    # Episode id -> when it was watched.
    watched: dict[uuid.UUID, dt.datetime]


class MovieTrackingResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    status: TrackingStatus
    watched_at: dt.datetime | None


class MediaResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    tmdb_id: int
    title: str
    overview: str
    poster_path: str | None
    backdrop_path: str | None
    network: str | None
    runtime: int | None
    release_date: dt.date | None
    tmdb_status: str | None


class NextEpisodeResponse(EpisodeResponse):
    # Aired regular episodes after it that the user has not watched.
    remaining: int


class ShowResponse(MediaResponse):
    seasons: list[SeasonResponse]
    tracking: ShowTrackingResponse | None
    # The episode to watch next, as on the watch list (in the user's time zone); None when the show is not in
    # progress or nothing aired is left.
    next_episode: NextEpisodeResponse | None


class MovieResponse(MediaResponse):
    tracking: MovieTrackingResponse | None


@contextlib.contextmanager
def tmdb_errors() -> collections.abc.Generator[None]:
    try:
        yield
    except TMDBNotFoundError:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "Not found on TMDB") from None
    except TMDBNotConfiguredError as error:
        raise fastapi.HTTPException(fastapi.status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except TMDBError:
        raise fastapi.HTTPException(fastapi.status.HTTP_502_BAD_GATEWAY, "TMDB cannot be reached") from None


async def cached_media(
    session: AsyncSession, tmdb: TMDBClientDepType, media_type: MediaType, tmdb_id: int, now: dt.datetime
) -> Media:
    """The media from the cache or TMDB; a stale one gets a refresh deferred in this transaction."""
    with tmdb_errors():
        return await CatalogManager(session, tmdb).get_or_fetch(media_type, tmdb_id, now)


@router.get("/search")
async def search(
    query: typing.Annotated[str, fastapi.Query(min_length=1, max_length=200)],
    user: CurrentUserDepType,
    session: DbSessionDepType,
    tmdb: TMDBClientDepType,
    media_type: MediaTypeQuery = MediaType.TV,
) -> list[SearchResult]:
    """TMDB's first page of shows (anime included) or movies."""
    with tmdb_errors():
        hits = await CatalogManager(session, tmdb).search(user, query, media_type)
    return [SearchResult.of(hit) for hit in hits]


@router.get("/discover/trending")
async def trending(
    media_type: MediaTypeQuery, user: CurrentUserDepType, session: DbSessionDepType, tmdb: TMDBClientDepType
) -> list[SearchResult]:
    """The week's trending shows or movies on TMDB."""
    with tmdb_errors():
        hits = await CatalogManager(session, tmdb).trending(user, media_type, dt.datetime.now(dt.UTC))
    return [SearchResult.of(hit) for hit in hits]


@router.get("/shows/{tmdb_id}")
async def get_show(
    tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType, tmdb: TMDBClientDepType
) -> ShowResponse:
    """The show with its seasons in summary."""
    now = dt.datetime.now(dt.UTC)
    media = await cached_media(session, tmdb, MediaType.TV, tmdb_id, now)
    tracking_manager = TrackingManager(session)
    tracking = await tracking_manager.show_tracking(user, media)
    next_episode = None
    for card in await UpcomingManager(session).watch_list(user, now=now, media=media):
        episode = await session.get_one(Episode, card.episode_id)
        next_episode = NextEpisodeResponse(
            **EpisodeResponse.model_validate(episode).model_dump(), remaining=card.remaining
        )
    response = ShowResponse(
        **MediaResponse.model_validate(media).model_dump(),
        seasons=[SeasonResponse.model_validate(season) for season in await tracking_manager.seasons(user, media, now)],
        tracking=ShowTrackingResponse.model_validate(tracking) if tracking else None,
        next_episode=next_episode,
    )
    await session.commit()
    return response


@router.get(
    "/shows/{tmdb_id}/seasons/{season_number}",
    responses={fastapi.status.HTTP_404_NOT_FOUND: {"description": "Show not loaded, or no such season"}},
)
async def get_season(
    tmdb_id: TMDBId,
    season_number: typing.Annotated[int, fastapi.Path(ge=0)],
    session: DbSessionDepType,
) -> SeasonEpisodesResponse:
    """A season's episodes, of a show its page loaded."""
    media = await find_media(session, MediaType.TV, tmdb_id)
    season = (
        None
        if media is None
        else await session.scalar(
            sa.select(Season).where(Season.media_id == media.id, Season.season_number == season_number)
        )
    )
    if media is None or season is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "No such season")
    episodes = await session.scalars(
        sa.select(Episode)
        .where(Episode.media_id == media.id, Episode.season_number == season_number)
        .order_by(Episode.episode_number)
    )
    return SeasonEpisodesResponse(
        season_number=season.season_number,
        title=season.title,
        episodes=[EpisodeResponse.model_validate(episode) for episode in episodes],
    )


@router.get("/movies/{tmdb_id}")
async def get_movie(
    tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType, tmdb: TMDBClientDepType
) -> MovieResponse:
    media = await cached_media(session, tmdb, MediaType.MOVIE, tmdb_id, dt.datetime.now(dt.UTC))
    tracking = await TrackingManager(session).movie_tracking(user, media)
    await session.commit()
    return MovieResponse(
        **MediaResponse.model_validate(media).model_dump(),
        tracking=MovieTrackingResponse.model_validate(tracking) if tracking else None,
    )
