import datetime as dt
import typing
import uuid

import fastapi
import pydantic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.ratings.managers import RatingManager
from mintrack.core.tracking.managers import FutureWatchError, TrackingManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import Episode, Media, User, WatchedEpisode
from mintrack.server.api.catalog import EpisodeResponse, RatingResponse, ShowTrackingResponse
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(tags=["episodes"])

EpisodeId = typing.Annotated[uuid.UUID, fastapi.Path()]


class EpisodeDetailResponse(EpisodeResponse):
    """An episode as its sheet shows it, with its show and what the user did with it."""

    tmdb_id: int
    show_title: str
    network: str | None
    poster_path: str | None
    overview: str
    still_path: str | None
    # TMDB users' average score out of 10 and their number of votes, when known.
    vote_average: float | None
    vote_count: int | None
    watched_at: dt.datetime | None
    rating: RatingResponse | None


class WatchDateRequest(pydantic.BaseModel):
    watched_at: pydantic.AwareDatetime


async def episode_and_show(session: AsyncSession, episode_id: uuid.UUID) -> tuple[Episode, Media]:
    """Episodes exist only once their show's page loaded them into the catalog."""
    episode = await session.get(Episode, episode_id)
    if episode is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "No such episode")
    return episode, await session.get_one(Media, episode.media_id)


async def watched_at(session: AsyncSession, user: User, episode_id: uuid.UUID) -> dt.datetime | None:
    return await session.scalar(
        sa.select(WatchedEpisode.watched_at).where(
            WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id == episode_id
        )
    )


@router.get("/episodes/{episode_id}")
async def get_episode(
    episode_id: EpisodeId, user: CurrentUserDepType, session: DbSessionDepType
) -> EpisodeDetailResponse:
    episode, media = await episode_and_show(session, episode_id)
    rating = await RatingManager(session).episode_rating(user, episode.id)
    return EpisodeDetailResponse(
        **EpisodeResponse.model_validate(episode).model_dump(),
        tmdb_id=media.tmdb_id,
        show_title=media.title,
        network=media.network,
        poster_path=media.poster_path,
        overview=episode.overview,
        still_path=episode.still_path,
        vote_average=episode.vote_average,
        vote_count=episode.vote_count,
        watched_at=await watched_at(session, user, episode.id),
        rating=RatingResponse.model_validate(rating) if rating else None,
    )


@router.put(
    "/episodes/{episode_id}/watched",
    responses={fastapi.status.HTTP_404_NOT_FOUND: {"description": "No such episode, or not watched"}},
)
async def change_watch_date(
    episode_id: EpisodeId, body: WatchDateRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> ShowTrackingResponse:
    """Date the user's watch of the episode differently; a date after now is refused."""
    episode, media = await episode_and_show(session, episode_id)
    try:
        tracking = await TrackingManager(session).change_watch_date(
            user, media, episode.id, body.watched_at, now=dt.datetime.now(dt.UTC)
        )
    except FutureWatchError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "The date is in the future"
        ) from None
    if tracking is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "Not watched")
    await session.commit()
    return ShowTrackingResponse.model_validate(tracking)
