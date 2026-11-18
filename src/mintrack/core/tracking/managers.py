import collections.abc
import dataclasses
import datetime as dt
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import ENDED_STATUSES
from mintrack.db.models import (
    Episode,
    Media,
    MediaType,
    TrackingStatus,
    User,
    UserMedia,
    WatchedEpisode,
    WatchedMovie,
)

from .statuses import SPECIALS_SEASON, EpisodeProgress, air_time_known, is_aired, show_status


class UnknownEpisodesError(Exception):
    """Some episode ids do not belong to the show."""


@dataclasses.dataclass(frozen=True)
class ShowTracking:
    status: TrackingStatus
    watched: dict[uuid.UUID, dt.datetime]


@dataclasses.dataclass(frozen=True)
class MovieTracking:
    status: TrackingStatus
    watched_at: dt.datetime | None


@dataclasses.dataclass(frozen=True)
class LibraryItem:
    media: Media
    status: TrackingStatus
    watched_count: int
    aired_count: int
    updated_at: dt.datetime


class TrackingManager:
    """What each user watched, and the status of each show and movie in their library."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mark_watched(self, user: User, episode: Episode, at: dt.datetime) -> ShowTracking:
        media = await self.session.get_one(Media, episode.media_id)
        return await self.mark_episodes(user, media, [episode.id], at)

    async def unmark_watched(self, user: User, episode: Episode, now: dt.datetime) -> ShowTracking | None:
        media = await self.session.get_one(Media, episode.media_id)
        return await self.unmark_episodes(user, media, [episode.id], now)

    async def mark_episodes(
        self, user: User, media: Media, episode_ids: collections.abc.Collection[uuid.UUID], at: dt.datetime
    ) -> ShowTracking:
        """Mark episodes watched at `at`; the show joins the library and leaves stopped."""
        await self._check_episodes(media, episode_ids)
        await self.session.execute(
            insert(WatchedEpisode)
            .values([{"user_id": user.id, "episode_id": episode_id, "watched_at": at} for episode_id in episode_ids])
            .on_conflict_do_nothing()
        )
        user_media = await self._track(user, media, at)
        if user_media.status is TrackingStatus.STOPPED:
            user_media.status = TrackingStatus.WATCHING
        return await self._update_show_status(user, media, user_media, at)

    async def unmark_episodes(
        self, user: User, media: Media, episode_ids: collections.abc.Collection[uuid.UUID], now: dt.datetime
    ) -> ShowTracking | None:
        """Unmark episodes; None when the show is not in the library."""
        await self._check_episodes(media, episode_ids)
        await self.session.execute(
            sa.delete(WatchedEpisode).where(
                WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id.in_(episode_ids)
            )
        )
        user_media = await self._locked(user, media)
        return await self._update_show_status(user, media, user_media, now) if user_media else None

    async def track_show(self, user: User, media: Media, *, stopped: bool, now: dt.datetime) -> ShowTracking:
        """Add the show to the library, stop it or resume it."""
        user_media = await self._track(user, media, now)
        user_media.status = TrackingStatus.STOPPED if stopped else TrackingStatus.WATCHING
        return await self._update_show_status(user, media, user_media, now)

    async def set_movie_watched(self, user: User, media: Media, *, watched: bool, now: dt.datetime) -> MovieTracking:
        """Add the movie to the library, as watched at `now` or to watch later."""
        user_media = await self._track(user, media, now)
        if watched:
            await self.session.execute(
                insert(WatchedMovie).values(user_id=user.id, media_id=media.id, watched_at=now).on_conflict_do_nothing()
            )
        else:
            await self.session.execute(
                sa.delete(WatchedMovie).where(WatchedMovie.user_id == user.id, WatchedMovie.media_id == media.id)
            )
        user_media.status = TrackingStatus.WATCHED if watched else TrackingStatus.WATCH_LATER
        user_media.updated_at = max(user_media.updated_at, now)
        await self.session.flush()
        return MovieTracking(status=user_media.status, watched_at=await self._movie_watched_at(user, media))

    async def untrack(self, user: User, media: Media) -> None:
        """Remove the media from the library, with what the user watched of it."""
        await self.session.execute(
            sa.delete(WatchedEpisode).where(
                WatchedEpisode.user_id == user.id,
                WatchedEpisode.episode_id.in_(sa.select(Episode.id).where(Episode.media_id == media.id)),
            )
        )
        for model in (WatchedMovie, UserMedia):
            await self.session.execute(sa.delete(model).where(model.user_id == user.id, model.media_id == media.id))

    async def show_tracking(self, user: User, media: Media) -> ShowTracking | None:
        user_media = await self.session.get(UserMedia, (user.id, media.id))
        if user_media is None:
            return None
        return ShowTracking(status=user_media.status, watched=await self._watched(user, media))

    async def movie_tracking(self, user: User, media: Media) -> MovieTracking | None:
        user_media = await self.session.get(UserMedia, (user.id, media.id))
        if user_media is None:
            return None
        return MovieTracking(status=user_media.status, watched_at=await self._movie_watched_at(user, media))

    async def refresh_statuses(self, media: Media, now: dt.datetime) -> None:
        """Recompute the show's status for every user tracking it, after its episodes changed or aired."""
        if media.media_type is not MediaType.TV:
            return
        rows = await self.session.execute(
            sa.select(User, UserMedia)
            .join(UserMedia, UserMedia.user_id == User.id)
            .where(UserMedia.media_id == media.id)
        )
        for user, user_media in rows:
            await self._update_show_status(user, media, user_media, now, touch=False)

    async def library(self, user: User, media_type: MediaType, now: dt.datetime) -> list[LibraryItem]:
        today = now.astimezone(zoneinfo.ZoneInfo(user.timezone)).date()
        regular = sa.and_(Episode.media_id == Media.id, Episode.season_number != SPECIALS_SEASON)
        aired = sa.case((Episode.airstamp.is_not(None), Episode.airstamp <= now), else_=Episode.air_date <= today)
        aired_count = sa.select(sa.func.count()).where(regular, aired).scalar_subquery()
        watched_count = (
            sa.select(sa.func.count())
            .select_from(WatchedEpisode)
            .join(Episode, Episode.id == WatchedEpisode.episode_id)
            .where(regular, aired, WatchedEpisode.user_id == user.id)
            .scalar_subquery()
        )
        rows = await self.session.execute(
            sa.select(Media, UserMedia.status, watched_count, aired_count, UserMedia.updated_at)
            .join(UserMedia, UserMedia.media_id == Media.id)
            .where(UserMedia.user_id == user.id, Media.media_type == media_type)
            .order_by(UserMedia.updated_at.desc())
        )
        return [LibraryItem(*row) for row in rows]

    async def _track(self, user: User, media: Media, now: dt.datetime) -> UserMedia:
        """The library row, created when missing and locked like `_locked`."""
        statement = insert(UserMedia).values(
            user_id=user.id, media_id=media.id, status=TrackingStatus.WATCH_LATER, updated_at=now
        )
        result = await self.session.scalars(
            # An update that changes nothing, so the row is returned and locked whether it existed or not.
            statement.on_conflict_do_update(
                index_elements=[UserMedia.user_id, UserMedia.media_id], set_={"user_id": statement.excluded.user_id}
            )
            .returning(UserMedia)
            .execution_options(populate_existing=True)
        )
        return result.one()

    async def _check_episodes(self, media: Media, episode_ids: collections.abc.Collection[uuid.UUID]) -> None:
        known = await self.session.scalar(
            sa.select(sa.func.count()).where(Episode.id.in_(episode_ids), Episode.media_id == media.id)
        )
        if not episode_ids or known != len(set(episode_ids)):
            raise UnknownEpisodesError

    async def _movie_watched_at(self, user: User, media: Media) -> dt.datetime | None:
        return await self.session.scalar(
            sa.select(WatchedMovie.watched_at).where(WatchedMovie.user_id == user.id, WatchedMovie.media_id == media.id)
        )

    async def _locked(self, user: User, media: Media) -> UserMedia | None:
        """The library row, locked until the transaction ends so concurrent writes compute the status in turn."""
        return await self.session.scalar(
            sa.select(UserMedia)
            .where(UserMedia.user_id == user.id, UserMedia.media_id == media.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _watched(self, user: User, media: Media) -> dict[uuid.UUID, dt.datetime]:
        rows = await self.session.execute(
            sa.select(WatchedEpisode.episode_id, WatchedEpisode.watched_at)
            .join(Episode, Episode.id == WatchedEpisode.episode_id)
            .where(WatchedEpisode.user_id == user.id, Episode.media_id == media.id)
        )
        return dict(rows.all())

    async def _update_show_status(
        self, user: User, media: Media, user_media: UserMedia, now: dt.datetime, *, touch: bool = True
    ) -> ShowTracking:
        timezone = zoneinfo.ZoneInfo(user.timezone)
        watched = await self._watched(user, media)
        episodes = await self.session.execute(
            sa.select(Episode.id, Episode.air_date, Episode.airstamp).where(
                Episode.media_id == media.id, Episode.season_number != SPECIALS_SEASON
            )
        )
        progress = []
        for episode_id, air_date, airstamp in episodes:
            aired = is_aired(air_date, airstamp, now, timezone)
            upcoming = not aired and air_time_known(air_date, airstamp)
            progress.append(EpisodeProgress(aired=aired, upcoming=upcoming, watched=episode_id in watched))
        user_media.status = show_status(user_media.status, progress, ended=media.tmdb_status in ENDED_STATUSES)
        if touch:
            # Imports mark with past dates: the library keeps its most recent activity first.
            user_media.updated_at = max(user_media.updated_at, now)
        await self.session.flush()
        return ShowTracking(status=user_media.status, watched=watched)
