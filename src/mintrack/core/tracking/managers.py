import collections.abc
import dataclasses
import datetime as dt
import enum
import itertools
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import ENDED_STATUSES, INSERT_BATCH, is_airing
from mintrack.db.models import (
    Episode,
    EpisodeRating,
    Media,
    MediaRating,
    MediaType,
    Season,
    TrackingStatus,
    User,
    UserMedia,
    WatchedEpisode,
    WatchedMovie,
)
from mintrack.worker.defer import defer_air_times_refresh

from .statuses import SPECIALS_SEASON, EpisodeProgress, air_time_known, is_aired, show_status


class UnknownEpisodesError(Exception):
    """Some episode ids do not belong to the show."""


class UnairedEpisodesError(Exception):
    """Some episodes air later."""


class FutureWatchError(Exception):
    """A watch dated after now."""


class ShowTrackingChoice(enum.StrEnum):
    """The statuses a user sets on a show; the others follow from the episodes watched."""

    WATCHING = enum.auto()
    WATCH_LATER = enum.auto()
    STOPPED = enum.auto()


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


@dataclasses.dataclass(frozen=True)
class SeasonSummary:
    season_number: int
    title: str
    episode_count: int
    watched_count: int
    # Aired episodes, and watched ones not aired as far as their date says.
    aired_count: int


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
    # The user finished the show; always False for movies.
    finished: bool
    # The user's stars for the episode or the movie, if rated.
    rating: int | None


class TrackingManager:
    """What each user watched, and the status of each show and movie in their library."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mark_episodes(
        self,
        user: User,
        media: Media,
        episode_ids: collections.abc.Collection[uuid.UUID],
        at: dt.datetime,
        *,
        now: dt.datetime,
    ) -> ShowTracking:
        """Mark episodes watched at `at`; the show joins the library and leaves stopped or watch later.

        Raises `UnknownEpisodesError`, `UnairedEpisodesError` for an episode airing after `now`, and
        `FutureWatchError` when `at` is after `now`.
        """
        if at > now:
            raise FutureWatchError
        await self._check_episodes(media, episode_ids)
        await self._check_aired(user, media, episode_ids, now)
        await self._insert_watches([(episode_id, at) for episode_id in episode_ids], user)
        user_media = await self._track(user, media, at)
        user_media.updated_at = max(user_media.updated_at, at)
        _resume(user_media)
        return await self._update_show_status(user, media, user_media, now, touch=False)

    async def record_watches(
        self,
        user: User,
        shows: collections.abc.Mapping[Media, collections.abc.Mapping[uuid.UUID, dt.datetime]],
        *,
        now: dt.datetime,
        keep_aside: collections.abc.Container[uuid.UUID] = (),
    ) -> None:
        """Mark many episodes of many shows, each `{episode id: watched at}` from the show's own episodes, in a few
        statements: a date after `now` is now's, each show joins the library, resumes unless its media id is in
        `keep_aside`, and gets its status once."""
        watches = [(episode_id, min(at, now)) for episodes in shows.values() for episode_id, at in episodes.items()]
        for batch in itertools.batched(watches, INSERT_BATCH, strict=False):
            await self._insert_watches(batch, user)
        for media, episodes in shows.items():
            dates = [min(at, now) for at in episodes.values()]
            user_media = await self._track(user, media, min(dates))
            # Imports mark with past dates: the library keeps its most recent activity first.
            user_media.updated_at = max(user_media.updated_at, *dates)
            if media.id not in keep_aside:
                _resume(user_media)
            await self._update_show_status(user, media, user_media, now, touch=False)

    async def _insert_watches(
        self, watches: collections.abc.Sequence[tuple[uuid.UUID, dt.datetime]], user: User
    ) -> None:
        """A watch already recorded keeps its date."""
        if watches:
            await self.session.execute(
                insert(WatchedEpisode)
                .values(
                    [{"user_id": user.id, "episode_id": episode_id, "watched_at": at} for episode_id, at in watches]
                )
                .on_conflict_do_nothing()
            )

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

    async def change_watch_date(
        self, user: User, media: Media, episode_id: uuid.UUID, at: dt.datetime, *, now: dt.datetime
    ) -> ShowTracking | None:
        """Date the user's watch of the episode `at`; None when they have not watched it.

        Raises `UnknownEpisodesError` and, when `at` is after `now`, `FutureWatchError`.
        """
        if at > now:
            raise FutureWatchError
        await self._check_episodes(media, [episode_id])
        changed = await self.session.scalar(
            sa.update(WatchedEpisode)
            .where(WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id == episode_id)
            .values(watched_at=at)
            .returning(WatchedEpisode.episode_id)
        )
        return None if changed is None else await self.show_tracking(user, media)

    async def set_show_status(
        self, user: User, media: Media, status: ShowTrackingChoice, now: dt.datetime
    ) -> ShowTracking:
        """Add the show to the library, put it aside to watch later (out of the watch list until an episode is marked
        or the show is resumed), stop it or resume it."""
        user_media = await self._track(user, media, now)
        user_media.status = {
            ShowTrackingChoice.WATCHING: TrackingStatus.WATCHING,
            ShowTrackingChoice.WATCH_LATER: TrackingStatus.WATCH_LATER,
            ShowTrackingChoice.STOPPED: TrackingStatus.STOPPED,
        }[status]
        if status is ShowTrackingChoice.WATCHING and is_airing(media):
            # Exact air times, before the next daily refresh.
            await defer_air_times_refresh(self.session, media.id)
        return await self._update_show_status(user, media, user_media, now)

    async def set_movie_watched(
        self, user: User, media: Media, *, watched: bool, at: dt.datetime, now: dt.datetime
    ) -> MovieTracking:
        """Add the movie to the library, as watched at `at` or to watch later; `FutureWatchError` when `at` is after
        `now`."""
        if watched and at > now:
            raise FutureWatchError
        user_media = await self._track(user, media, at)
        if watched:
            await self.session.execute(
                insert(WatchedMovie).values(user_id=user.id, media_id=media.id, watched_at=at).on_conflict_do_nothing()
            )
        else:
            await self.session.execute(
                sa.delete(WatchedMovie).where(WatchedMovie.user_id == user.id, WatchedMovie.media_id == media.id)
            )
        user_media.status = TrackingStatus.WATCHED if watched else TrackingStatus.WATCH_LATER
        user_media.updated_at = max(user_media.updated_at, at)
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

    async def seasons(self, user: User, media: Media, now: dt.datetime) -> list[SeasonSummary]:
        """The show's seasons with their episode counts for the user, specials last as on TMDB."""
        watched = WatchedEpisode.episode_id.is_not(None)
        counts = (
            sa.select(
                Episode.season_number,
                sa.func.count().label("episode_count"),
                sa.func.count().filter(watched).label("watched_count"),
                sa.func.count().filter(sa.or_(watched, _aired(user, now))).label("aired_count"),
            )
            .outerjoin(WatchedEpisode, (WatchedEpisode.episode_id == Episode.id) & (WatchedEpisode.user_id == user.id))
            .where(Episode.media_id == media.id)
            .group_by(Episode.season_number)
            .subquery()
        )
        rows = await self.session.execute(
            sa.select(
                Season.season_number,
                Season.title,
                sa.func.coalesce(counts.c.episode_count, 0),
                sa.func.coalesce(counts.c.watched_count, 0),
                sa.func.coalesce(counts.c.aired_count, 0),
            )
            .outerjoin(counts, counts.c.season_number == Season.season_number)
            .where(Season.media_id == media.id)
            .order_by(Season.season_number == SPECIALS_SEASON, Season.season_number)
        )
        return [SeasonSummary(*row) for row in rows]

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
            .order_by(UserMedia.user_id)
            # A status set concurrently (stopped, put aside) waits for this transaction, then applies.
            .with_for_update(of=UserMedia)
            .execution_options(populate_existing=True)
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
        status: TrackingStatus | None = None,
    ) -> list[LibraryItem]:
        if media_type is MediaType.MOVIE:
            counts = (
                sa.select(
                    WatchedMovie.media_id,
                    sa.literal(0).label("watched_count"),
                    sa.literal(0).label("aired_count"),
                    WatchedMovie.watched_at.label("last_watched_at"),
                )
                .where(WatchedMovie.user_id == user.id)
                .subquery()
            )
        else:
            regular_aired = sa.and_(Episode.season_number != SPECIALS_SEASON, _aired(user, now))
            counts = (
                sa.select(
                    Episode.media_id,
                    sa.func.count(WatchedEpisode.episode_id).filter(regular_aired).label("watched_count"),
                    sa.func.count().filter(regular_aired).label("aired_count"),
                    sa.func.max(WatchedEpisode.watched_at).label("last_watched_at"),
                )
                .outerjoin(
                    WatchedEpisode, (WatchedEpisode.episode_id == Episode.id) & (WatchedEpisode.user_id == user.id)
                )
                .where(Episode.media_id.in_(sa.select(UserMedia.media_id).where(UserMedia.user_id == user.id)))
                .group_by(Episode.media_id)
                .subquery()
            )
        last_watched_at = counts.c.last_watched_at
        query = (
            sa.select(
                Media,
                UserMedia.status,
                sa.func.coalesce(counts.c.watched_count, 0),
                sa.func.coalesce(counts.c.aired_count, 0),
                UserMedia.updated_at,
                UserMedia.added_at,
                last_watched_at,
            )
            .join(UserMedia, UserMedia.media_id == Media.id)
            .outerjoin(counts, counts.c.media_id == Media.id)
            .where(UserMedia.user_id == user.id, Media.media_type == media_type)
        )
        if status is not None:
            query = query.where(UserMedia.status == status)
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
                sa.func.coalesce(UserMedia.status == TrackingStatus.FINISHED, sa.false()).label("finished"),
                EpisodeRating.stars.label("rating"),
            )
            .join(Episode, Episode.id == WatchedEpisode.episode_id)
            .join(Media, Media.id == Episode.media_id)
            .outerjoin(UserMedia, (UserMedia.user_id == user.id) & (UserMedia.media_id == Media.id))
            .outerjoin(EpisodeRating, (EpisodeRating.user_id == user.id) & (EpisodeRating.episode_id == Episode.id))
            .where(WatchedEpisode.user_id == user.id)
        )
        movies = (
            sa.select(
                WatchedMovie.media_id,
                Media.media_type,
                Media.tmdb_id,
                Media.title,
                Media.poster_path,
                sa.cast(sa.null(), sa.Integer).label("season_number"),
                sa.cast(sa.null(), sa.Integer).label("episode_number"),
                sa.cast(sa.null(), sa.TEXT).label("episode_title"),
                WatchedMovie.watched_at,
                sa.false().label("finished"),
                MediaRating.stars.label("rating"),
            )
            .join(Media, Media.id == WatchedMovie.media_id)
            .outerjoin(MediaRating, (MediaRating.user_id == user.id) & (MediaRating.media_id == Media.id))
            .where(WatchedMovie.user_id == user.id)
        )
        if before is not None:
            cursor = sa.tuple_(sa.literal(before[0], sa.TIMESTAMP(timezone=True)), sa.literal(before[1], sa.Uuid))
            episodes = episodes.where(sa.tuple_(WatchedEpisode.watched_at, WatchedEpisode.episode_id) < cursor)
            movies = movies.where(sa.tuple_(WatchedMovie.watched_at, WatchedMovie.media_id) < cursor)
        # Each side reads only its page from its (user, watched at, id) index before the union is sorted.
        episodes = episodes.order_by(WatchedEpisode.watched_at.desc(), WatchedEpisode.episode_id.desc()).limit(limit)
        movies = movies.order_by(WatchedMovie.watched_at.desc(), WatchedMovie.media_id.desc()).limit(limit)
        watched = sa.union_all(sa.select(episodes.subquery()), sa.select(movies.subquery())).subquery()
        rows = await self.session.execute(
            sa.select(watched).order_by(watched.c.watched_at.desc(), watched.c.id.desc()).limit(limit)
        )
        return [HistoryEntry(*row) for row in rows]

    async def _track(self, user: User, media: Media, now: dt.datetime) -> UserMedia:
        """The library row, created when missing and locked like `_locked`."""
        status = TrackingStatus.NOT_STARTED if media.media_type is MediaType.TV else TrackingStatus.WATCH_LATER
        statement = insert(UserMedia).values(
            user_id=user.id, media_id=media.id, status=status, added_at=now, updated_at=now
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

    async def _check_aired(
        self, user: User, media: Media, episode_ids: collections.abc.Collection[uuid.UUID], now: dt.datetime
    ) -> None:
        """Raise `UnairedEpisodesError` when an episode airs after `now`; one without a date may have aired."""
        timezone = zoneinfo.ZoneInfo(user.timezone)
        episodes = await self.session.execute(
            sa.select(Episode.air_date, Episode.airstamp).where(
                Episode.id.in_(episode_ids), Episode.media_id == media.id
            )
        )
        if any(
            air_time_known(air_date, airstamp) and not is_aired(air_date, airstamp, now, timezone)
            for air_date, airstamp in episodes
        ):
            raise UnairedEpisodesError

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
            user_media.updated_at = max(user_media.updated_at, now)
        await self.session.flush()
        return ShowTracking(status=user_media.status, watched=watched)


def _aired(user: User, now: dt.datetime) -> sa.ColumnElement[bool]:
    """`is_aired` in SQL: NULL, which counts as not aired, without a date."""
    today = now.astimezone(zoneinfo.ZoneInfo(user.timezone)).date()
    return sa.case((Episode.airstamp.is_not(None), Episode.airstamp <= now), else_=Episode.air_date <= today)


def _resume(user_media: UserMedia) -> None:
    """A show stopped or put aside is watched again."""
    if user_media.status in (TrackingStatus.STOPPED, TrackingStatus.WATCH_LATER):
        user_media.status = TrackingStatus.WATCHING
