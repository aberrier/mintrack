import collections.abc
import contextlib
import datetime as dt
import itertools
import typing
import uuid

import fastapi
import pydantic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager, SearchHit, is_stale
from mintrack.core.tracking.managers import MovieTracking, ShowTracking, TrackingManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import Episode, Media, MediaType, Season, TrackingStatus, User
from mintrack.integrations.tmdb.client import TMDBError, TMDBNotConfiguredError, TMDBNotFoundError
from mintrack.server.api.dependencies import CurrentUserDepType, TMDBClientDepType
from mintrack.worker.tasks import defer_refresh

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
    season_number: int
    title: str
    episodes: list[EpisodeResponse]


class ShowTrackingResponse(pydantic.BaseModel):
    status: TrackingStatus
    # Episode id -> when it was watched.
    watched: dict[uuid.UUID, dt.datetime]

    @classmethod
    def of(cls, tracking: ShowTracking) -> typing.Self:
        return cls(status=tracking.status, watched=tracking.watched)


class MovieTrackingResponse(pydantic.BaseModel):
    status: TrackingStatus
    watched_at: dt.datetime | None

    @classmethod
    def of(cls, tracking: MovieTracking) -> typing.Self:
        return cls(status=tracking.status, watched_at=tracking.watched_at)


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


class ShowResponse(MediaResponse):
    seasons: list[SeasonResponse]
    tracking: ShowTrackingResponse | None


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


async def seasons_of(session: AsyncSession, media: Media) -> list[SeasonResponse]:
    seasons = await session.scalars(sa.select(Season).where(Season.media_id == media.id))
    episodes = await session.scalars(
        sa.select(Episode).where(Episode.media_id == media.id).order_by(Episode.season_number, Episode.episode_number)
    )
    by_season = {number: list(group) for number, group in itertools.groupby(episodes, lambda e: e.season_number)}
    return [
        SeasonResponse(
            season_number=season.season_number,
            title=season.title,
            episodes=[EpisodeResponse.model_validate(episode) for episode in by_season.get(season.season_number, [])],
        )
        # Specials last, as on TMDB.
        for season in sorted(seasons, key=lambda season: (season.season_number == 0, season.season_number))
    ]


async def cached_media(
    session: AsyncSession, tmdb: TMDBClientDepType, media_type: MediaType, tmdb_id: int, now: dt.datetime
) -> Media:
    """The media from the cache or TMDB; a stale one gets a refresh deferred in this transaction."""
    with tmdb_errors():
        media = await CatalogManager(session, tmdb).get_or_fetch(media_type, tmdb_id, now)
    if tmdb.configured and is_stale(media, now):
        await defer_refresh(session, media.id)
    return media


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


async def show_response(session: AsyncSession, user: User, media: Media) -> ShowResponse:
    tracking = await TrackingManager(session).show_tracking(user, media)
    return ShowResponse(
        **MediaResponse.model_validate(media).model_dump(),
        seasons=await seasons_of(session, media),
        tracking=ShowTrackingResponse.of(tracking) if tracking else None,
    )


@router.get("/shows/{tmdb_id}")
async def get_show(
    tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType, tmdb: TMDBClientDepType
) -> ShowResponse:
    media = await cached_media(session, tmdb, MediaType.TV, tmdb_id, dt.datetime.now(dt.UTC))
    response = await show_response(session, user, media)
    await session.commit()
    return response


@router.get("/movies/{tmdb_id}")
async def get_movie(
    tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType, tmdb: TMDBClientDepType
) -> MovieResponse:
    media = await cached_media(session, tmdb, MediaType.MOVIE, tmdb_id, dt.datetime.now(dt.UTC))
    tracking = await TrackingManager(session).movie_tracking(user, media)
    await session.commit()
    return MovieResponse(
        **MediaResponse.model_validate(media).model_dump(),
        tracking=MovieTrackingResponse.of(tracking) if tracking else None,
    )
