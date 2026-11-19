import datetime as dt
import typing
import uuid

import fastapi
import pydantic

from mintrack.core.tracking.managers import (
    LibrarySort,
    ShowTrackingChoice,
    TrackingManager,
    UnairedEpisodesError,
    UnknownEpisodesError,
)
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import MediaType, TrackingStatus
from mintrack.server.api.catalog import MovieTrackingResponse, ShowTrackingResponse, TMDBId
from mintrack.server.api.common import cached
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(tags=["tracking"])

MAX_EPISODES_PER_REQUEST = 2000
DEFAULT_HISTORY_PAGE = 30
MAX_HISTORY_PAGE = 100


class ShowTrackingRequest(pydantic.BaseModel):
    # An unknown field is refused rather than ignored.
    model_config = pydantic.ConfigDict(extra="forbid")

    status: ShowTrackingChoice = ShowTrackingChoice.WATCHING


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
    added_at: dt.datetime
    last_watched_at: dt.datetime | None


class HistoryEntryResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    # The episode's id, or the movie's: with watched_at, the cursor of the next page.
    id: uuid.UUID
    media_type: MediaType
    tmdb_id: int
    title: str
    poster_path: str | None
    season_number: int | None
    episode_number: int | None
    episode_title: str | None
    watched_at: dt.datetime
    # The user finished the show; always false for movies.
    finished: bool
    # The user's stars for the episode or the movie, if rated.
    stars: int | None


class HistoryResponse(pydantic.BaseModel):
    entries: list[HistoryEntryResponse]
    has_more: bool


@router.put("/shows/{tmdb_id}/tracking")
async def track_show(
    tmdb_id: TMDBId,
    body: ShowTrackingRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> ShowTrackingResponse:
    """Add the show to the library, put it aside to watch later, stop it or resume it."""
    media = await cached(session, MediaType.TV, tmdb_id)
    tracking = await TrackingManager(session).set_show_status(user, media, body.status, dt.datetime.now(dt.UTC))
    await session.commit()
    return ShowTrackingResponse.model_validate(tracking)


@router.post("/shows/{tmdb_id}/watched")
async def set_episodes_watched(
    tmdb_id: TMDBId,
    body: WatchedEpisodesRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> ShowTrackingResponse | None:
    """Mark episodes watched now, or unmark them; marking adds the show to the library. Episodes dated later
    cannot be marked."""
    media = await cached(session, MediaType.TV, tmdb_id)
    try:
        manager, now = TrackingManager(session), dt.datetime.now(dt.UTC)
        if body.watched:
            tracking = await manager.mark_episodes(user, media, body.episode_ids, now, now=now)
        else:
            tracking = await manager.unmark_episodes(user, media, body.episode_ids, now)
    except UnknownEpisodesError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "Some episodes are not episodes of this show"
        ) from None
    except UnairedEpisodesError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "Some episodes have not aired yet"
        ) from None
    await session.commit()
    return ShowTrackingResponse.model_validate(tracking) if tracking else None


@router.put("/movies/{tmdb_id}/tracking")
async def track_movie(
    tmdb_id: TMDBId,
    body: MovieTrackingRequest,
    user: CurrentUserDepType,
    session: DbSessionDepType,
) -> MovieTrackingResponse:
    """Add the movie to the library, watched now or to watch later."""
    media = await cached(session, MediaType.MOVIE, tmdb_id)
    now = dt.datetime.now(dt.UTC)
    tracking = await TrackingManager(session).set_movie_watched(user, media, watched=body.watched, at=now, now=now)
    await session.commit()
    return MovieTrackingResponse.model_validate(tracking)


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
    media_type: MediaType,
    user: CurrentUserDepType,
    session: DbSessionDepType,
    sort: LibrarySort = LibrarySort.LAST_WATCHED,
    status: TrackingStatus | None = None,
) -> list[LibraryItemResponse]:
    items = await TrackingManager(session).library(user, media_type, dt.datetime.now(dt.UTC), sort=sort, status=status)
    return [
        LibraryItemResponse(
            tmdb_id=item.media.tmdb_id,
            media_type=item.media.media_type,
            title=item.media.title,
            poster_path=item.media.poster_path,
            status=item.status,
            watched_count=item.watched_count,
            aired_count=item.aired_count,
            added_at=item.added_at,
            last_watched_at=item.last_watched_at,
        )
        for item in items
    ]


@router.get("/history")
async def history(
    user: CurrentUserDepType,
    session: DbSessionDepType,
    before: pydantic.AwareDatetime | None = None,
    # Without it, the page starts strictly before `before`.
    before_id: uuid.UUID | None = None,
    limit: typing.Annotated[int, fastapi.Query(ge=1, le=MAX_HISTORY_PAGE)] = DEFAULT_HISTORY_PAGE,
) -> HistoryResponse:
    """The episodes and movies the user watched, newest first, a page at a time."""
    cursor = (before, before_id or uuid.UUID(int=0)) if before is not None else None
    entries = await TrackingManager(session).history(user, before=cursor, limit=limit + 1)
    return HistoryResponse(
        entries=[HistoryEntryResponse.model_validate(entry) for entry in entries[:limit]],
        has_more=len(entries) > limit,
    )
