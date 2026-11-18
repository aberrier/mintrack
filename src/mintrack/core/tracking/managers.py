import collections.abc
import dataclasses
import datetime as dt
import enum
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


class LibrarySort(enum.StrEnum):
    LAST_WATCHED = enum.auto()
    LAST_ADDED = enum.auto()
    TITLE = enum.auto()


class LibraryStatus(enum.StrEnum):
    """A tracking status, or not started: in the library with nothing watched."""

    WATCH_LATER = enum.auto()
    WATCHING = enum.auto()
    UP_TO_DATE = enum.auto()
    FINISHED = enum.auto()
    STOPPED = enum.auto()
    WATCHED = enum.auto()
    NOT_STARTED = enum.auto()


@dataclasses.dataclass(frozen=True)
class LibraryItem:
    media: Media
    status: TrackingStatus
    watched_count: int
    aired_count: int
    updated_at: dt.datetime
    added_at: dt.datetime
    last_watched_at: dt.datetime | None


@dataclasses.dataclass(frozen=True)
class HistoryEntry:
    # The episode's id, or the movie's media id.
    id: uuid.UUID
    media_type: MediaType
    tmdb_id: int
    title: str
    poster_path: str | None
    # None for movies.
    season_number: int | None
    episode_number: int | None
    episode_title: str | None
    watched_at: dt.datetime


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
        """Mark episodes watched at `at`; the show joins the library and leaves stopped or watch later."""
        await self._check_episodes(media, episode_ids)
        await self.session.execute(
            insert(WatchedEpisode)
            .values([{"user_id": user.id, "episode_id": episode_id, "watched_at": at} for episode_id in episode_ids])
            .on_conflict_do_nothing()
        )
        user_media = await self._track(user, media, at)
        if user_media.status in (TrackingStatus.STOPPED, TrackingStatus.WATCH_LATER):
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

    async def watch_later(self, user: User, media: Media, now: dt.datetime) -> ShowTracking:
        """Put the show aside, out of the watch list, until an episode is marked or the show is resumed."""
        user_media = await self._track(user, media, now)
        user_media.status = TrackingStatus.WATCH_LATER
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

    async def library(
        self,
        user: User,
        media_type: MediaType,
        now: dt.datetime,
        *,
        sort: LibrarySort = LibrarySort.LAST_WATCHED,
        status: LibraryStatus | None = None,
    ) -> list[LibraryItem]:
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
        if media_type is MediaType.MOVIE:
            last_watched_at = (
                sa.select(WatchedMovie.watched_at)
                .where(WatchedMovie.user_id == user.id, WatchedMovie.media_id == Media.id)
                .scalar_subquery()
            )
        else:
            last_watched_at = (
                sa.select(sa.func.max(WatchedEpisode.watched_at))
                .join(Episode, Episode.id == WatchedEpisode.episode_id)
                .where(WatchedEpisode.user_id == user.id, Episode.media_id == Media.id)
                .scalar_subquery()
            )
        query = (
            sa.select(
                Media,
                UserMedia.status,
                watched_count,
                aired_count,
                UserMedia.updated_at,
                UserMedia.added_at,
                last_watched_at,
            )
            .join(UserMedia, UserMedia.media_id == Media.id)
            .where(UserMedia.user_id == user.id, Media.media_type == media_type)
        )
        if status is LibraryStatus.NOT_STARTED:
            query = query.where(last_watched_at.is_(None))
        elif status is not None:
            query = query.where(UserMedia.status == TrackingStatus(status))
        order_by = {
            LibrarySort.LAST_WATCHED: (last_watched_at.desc().nulls_last(), UserMedia.updated_at.desc()),
            LibrarySort.LAST_ADDED: (UserMedia.added_at.desc(),),
            LibrarySort.TITLE: (sa.func.lower(Media.title), Media.title),
        }[sort]
        rows = await self.session.execute(query.order_by(*order_by, Media.id))
        return [LibraryItem(*row) for row in rows]

    async def history(
        self, user: User, *, before: tuple[dt.datetime, uuid.UUID] | None, limit: int
    ) -> list[HistoryEntry]:
        """The episodes and movies the user watched, newest first, from strictly before `before` (watched at, id)."""
        episodes = (
            sa.select(
                WatchedEpisode.episode_id.label("id"),
                Media.media_type,
                Media.tmdb_id,
                Media.title,
                Media.poster_path,
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
                WatchedEpisode.watched_at,
            )
            .join(Episode, Episode.id == WatchedEpisode.episode_id)
            .join(Media, Media.id == Episode.media_id)
            .where(WatchedEpisode.user_id == user.id)
        )
        movies = (
            sa.select(
                WatchedMovie.media_id,
                Media.media_type,
                Media.tmdb_id,
                Media.title,
                Media.poster_path,
                sa.cast(sa.null(), sa.Integer),
                sa.cast(sa.null(), sa.Integer),
                sa.cast(sa.null(), sa.TEXT),
                WatchedMovie.watched_at,
            )
            .join(Media, Media.id == WatchedMovie.media_id)
            .where(WatchedMovie.user_id == user.id)
        )
        if before is not None:
            cursor = sa.tuple_(sa.literal(before[0], sa.TIMESTAMP(timezone=True)), sa.literal(before[1], sa.Uuid))
            episodes = episodes.where(sa.tuple_(WatchedEpisode.watched_at, WatchedEpisode.episode_id) < cursor)
            movies = movies.where(sa.tuple_(WatchedMovie.watched_at, WatchedMovie.media_id) < cursor)
        watched = sa.union_all(episodes, movies).subquery()
        rows = await self.session.execute(
            sa.select(watched).order_by(watched.c.watched_at.desc(), watched.c.id.desc()).limit(limit)
        )
        return [HistoryEntry(*row) for row in rows]

    async def _track(self, user: User, media: Media, now: dt.datetime) -> UserMedia:
        """The library row, created when missing and locked like `_locked`."""
        statement = insert(UserMedia).values(
            user_id=user.id, media_id=media.id, status=TrackingStatus.WATCH_LATER, added_at=now, updated_at=now
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
