import dataclasses
import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import EpisodeRating, MediaRating, User


@dataclasses.dataclass(frozen=True)
class Rating:
    stars: int
    review: str


class RatingManager:
    """Each user's own ratings of shows, movies and episodes: 1 to 5 stars and a short review, private to them."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def media_rating(self, user: User, media_id: uuid.UUID) -> MediaRating | None:
        return await self.session.get(MediaRating, (user.id, media_id))

    async def episode_rating(self, user: User, episode_id: uuid.UUID) -> EpisodeRating | None:
        return await self.session.get(EpisodeRating, (user.id, episode_id))

    async def rate_media(self, user: User, media_id: uuid.UUID, rating: Rating, now: dt.datetime) -> MediaRating:
        return await self._upsert(MediaRating, {"user_id": user.id, "media_id": media_id}, rating, now)

    async def rate_episode(self, user: User, episode_id: uuid.UUID, rating: Rating, now: dt.datetime) -> EpisodeRating:
        return await self._upsert(EpisodeRating, {"user_id": user.id, "episode_id": episode_id}, rating, now)

    async def unrate_media(self, user: User, media_id: uuid.UUID) -> None:
        await self.session.execute(
            sa.delete(MediaRating).where(MediaRating.user_id == user.id, MediaRating.media_id == media_id)
        )

    async def unrate_episode(self, user: User, episode_id: uuid.UUID) -> None:
        await self.session.execute(
            sa.delete(EpisodeRating).where(EpisodeRating.user_id == user.id, EpisodeRating.episode_id == episode_id)
        )

    async def _upsert[R: (MediaRating, EpisodeRating)](
        self, model: type[R], keys: dict[str, uuid.UUID], rating: Rating, now: dt.datetime
    ) -> R:
        values = {"stars": rating.stars, "review": rating.review, "updated_at": now}
        statement = (
            insert(model)
            .values(**keys, **values)
            .on_conflict_do_update(index_elements=list(keys), set_=values)
            .returning(model)
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(statement)).one()
