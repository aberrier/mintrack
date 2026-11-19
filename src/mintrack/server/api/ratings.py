import datetime as dt
import typing

import fastapi
import pydantic

from mintrack.core.ratings.managers import Rating, RatingManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import MediaType
from mintrack.db.models.rating import MAX_REVIEW_LENGTH, MAX_STARS, MIN_STARS
from mintrack.server.api.catalog import RatingResponse, TMDBId
from mintrack.server.api.dependencies import CurrentUserDepType
from mintrack.server.api.episodes import EpisodeId, episode_and_show
from mintrack.server.api.tracking import cached

router = fastapi.APIRouter(tags=["ratings"])


class RatingRequest(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    stars: typing.Annotated[int, pydantic.Field(ge=MIN_STARS, le=MAX_STARS)]
    review: typing.Annotated[str, pydantic.StringConstraints(strip_whitespace=True, max_length=MAX_REVIEW_LENGTH)] = ""

    def rating(self) -> Rating:
        return Rating(stars=self.stars, review=self.review)


@router.put("/shows/{tmdb_id}/rating")
async def rate_show(
    tmdb_id: TMDBId, body: RatingRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> RatingResponse:
    media = await cached(session, MediaType.TV, tmdb_id)
    rating = await RatingManager(session).rate_media(user, media.id, body.rating(), dt.datetime.now(dt.UTC))
    await session.commit()
    return RatingResponse.model_validate(rating)


@router.delete("/shows/{tmdb_id}/rating", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unrate_show(tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    await RatingManager(session).unrate_media(user, (await cached(session, MediaType.TV, tmdb_id)).id)
    await session.commit()


@router.put("/movies/{tmdb_id}/rating")
async def rate_movie(
    tmdb_id: TMDBId, body: RatingRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> RatingResponse:
    media = await cached(session, MediaType.MOVIE, tmdb_id)
    rating = await RatingManager(session).rate_media(user, media.id, body.rating(), dt.datetime.now(dt.UTC))
    await session.commit()
    return RatingResponse.model_validate(rating)


@router.delete("/movies/{tmdb_id}/rating", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unrate_movie(tmdb_id: TMDBId, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    await RatingManager(session).unrate_media(user, (await cached(session, MediaType.MOVIE, tmdb_id)).id)
    await session.commit()


@router.put("/episodes/{episode_id}/rating")
async def rate_episode(
    episode_id: EpisodeId, body: RatingRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> RatingResponse:
    episode, _ = await episode_and_show(session, episode_id)
    rating = await RatingManager(session).rate_episode(user, episode.id, body.rating(), dt.datetime.now(dt.UTC))
    await session.commit()
    return RatingResponse.model_validate(rating)


@router.delete("/episodes/{episode_id}/rating", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unrate_episode(episode_id: EpisodeId, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    episode, _ = await episode_and_show(session, episode_id)
    await RatingManager(session).unrate_episode(user, episode.id)
    await session.commit()
