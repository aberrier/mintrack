import datetime as dt
import typing
import uuid

import fastapi
import pydantic
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import find_media, is_airing
from mintrack.core.tracking.managers import TrackingManager, UnknownEpisodesError
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import Media, MediaType, TrackingStatus
from mintrack.server.api.catalog import MovieTrackingResponse, ShowTrackingResponse, TMDBId
from mintrack.server.api.dependencies import CurrentUserDepType
from mintrack.worker.tasks import defer_air_times_refresh

router = fastapi.APIRouter(tags=["tracking"])

MAX_EPISODES_PER_REQUEST = 2000


class ShowTrackingRequest(pydantic.BaseModel):
    stopped: bool = False


class WatchedEpisodesRequest(pydantic.BaseModel):
    episode_ids: typing.Annotated[list[uuid.UUID], pydantic.Field(min_length=1, max_length=MAX_EPISODES_PER_REQUEST)]
    watched: bool


class MovieTrackingRequest(pydantic.BaseModel):
    watched: bool


class LibraryItemResponse(pydantic.BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    poster_path: str | None
    status: TrackingStatus
    # Regular episodes (specials excluded); 0 for movies.
    watched_count: int
    aired_count: int


async def cached(session: AsyncSession, media_type: MediaType, tmdb_id: int) -> Media:
    """Media are written only after their page loaded it into the cache."""
    media = await find_media(session, media_type, tmdb_id)
    if media is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "Not in the catalog")
    return media


@router.put("/shows/{tmdb_id}/tracking")
async def track_show(
    tmdb_id: TMDBId,
    body: ShowTrackingRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> ShowTrackingResponse:
    """Add the show to the library, stop it or resume it."""
    media = await cached(session, MediaType.TV, tmdb_id)
    tracking = await TrackingManager(session).track_show(user, media, stopped=body.stopped, now=dt.datetime.now(dt.UTC))
    if not body.stopped and is_airing(media):
        # Exact air times, before the next daily refresh.
        await defer_air_times_refresh(session, media.id)
    await session.commit()
    return ShowTrackingResponse.of(tracking)


@router.post("/shows/{tmdb_id}/watched")
async def set_episodes_watched(
    tmdb_id: TMDBId,
    body: WatchedEpisodesRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> ShowTrackingResponse | None:
    """Mark episodes watched now, or unmark them; marking adds the show to the library."""
    media = await cached(session, MediaType.TV, tmdb_id)
    try:
        manager, now = TrackingManager(session), dt.datetime.now(dt.UTC)
        if body.watched:
            tracking = await manager.mark_episodes(user, media, body.episode_ids, now)
        else:
            tracking = await manager.unmark_episodes(user, media, body.episode_ids, now)
    except UnknownEpisodesError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "Some episodes are not episodes of this show"
        ) from None
    await session.commit()
    return ShowTrackingResponse.of(tracking) if tracking else None


@router.put("/movies/{tmdb_id}/tracking")
async def track_movie(
    tmdb_id: TMDBId,
    body: MovieTrackingRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> MovieTrackingResponse:
    """Add the movie to the library, watched now or to watch later."""
    media = await cached(session, MediaType.MOVIE, tmdb_id)
    tracking = await TrackingManager(session).set_movie_watched(
        user, media, watched=body.watched, now=dt.datetime.now(dt.UTC)
    )
    await session.commit()
    return MovieTrackingResponse.of(tracking)


@router.delete("/shows/{tmdb_id}/tracking", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def untrack_show(tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    """Remove the show from the library, with the episodes watched."""
    await TrackingManager(session).untrack(user, await cached(session, MediaType.TV, tmdb_id))
    await session.commit()


@router.delete("/movies/{tmdb_id}/tracking", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def untrack_movie(tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    await TrackingManager(session).untrack(user, await cached(session, MediaType.MOVIE, tmdb_id))
    await session.commit()


@router.get("/library")
async def library(
    media_type: MediaType, user: CurrentUserDepType, session: DbSessionDepType
) -> list[LibraryItemResponse]:
    items = await TrackingManager(session).library(user, media_type, dt.datetime.now(dt.UTC))
    return [
        LibraryItemResponse(
            tmdb_id=item.media.tmdb_id,
            media_type=item.media.media_type,
            title=item.media.title,
            poster_path=item.media.poster_path,
            status=item.status,
            watched_count=item.watched_count,
            aired_count=item.aired_count,
        )
        for item in items
    ]
