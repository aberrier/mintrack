import dataclasses
import datetime as dt
import itertools
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import LateralFromClause

from mintrack.db.models import Episode, Media, TrackingStatus, User, UserMedia, WatchedEpisode

from .air_times import FOLLOWED_STATUSES

UPCOMING_DAYS = 28
IN_PROGRESS_STATUSES = (TrackingStatus.WATCHING, TrackingStatus.UP_TO_DATE)


@dataclasses.dataclass(frozen=True)
class UpcomingEpisode:
    episode_id: uuid.UUID
    tmdb_id: int
    show_title: str
    poster_path: str | None
    season_number: int
    episode_number: int
    title: str
    # Exact UTC air time from TVmaze; None when only the day is known.
    airstamp: dt.datetime | None
    # The air day in the user's time zone; None when unknown.
    day: dt.date | None


@dataclasses.dataclass(frozen=True)
class UpcomingDay:
    day: dt.date
    episodes: list[UpcomingEpisode]


@dataclasses.dataclass(frozen=True)
class Upcoming:
    new: list[UpcomingEpisode]
    days: list[UpcomingDay]


class UpcomingManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upcoming(self, user: User, *, now: dt.datetime) -> Upcoming:
        """Episodes airing from today over the coming weeks, grouped by day in the user's time zone.

        `new` holds the episodes of shows in progress aired before today and since the user last watched one, after
        the furthest one watched.
        """
        today = now.astimezone(zoneinfo.ZoneInfo(user.timezone)).date()
        moment, day = _air_moment(user.timezone), _air_day(user.timezone)
        last = _last_watched(user)

        coming = await self._episodes(
            user,
            FOLLOWED_STATUSES,
            day.between(today, today + dt.timedelta(days=UPCOMING_DAYS - 1)),
            ~_watched(user, Episode),
            order_by=(moment, Media.title, Episode.season_number, Episode.episode_number),
        )
        new = await self._episodes(
            user,
            IN_PROGRESS_STATUSES,
            day < today,
            Episode.season_number > 0,
            sa.tuple_(Episode.season_number, Episode.episode_number) > sa.tuple_(last.c.season_number, last.c.number),
            _aired_since(user, day),
            ~_watched(user, Episode),
            join_last=last,
            order_by=(moment, Media.title, Episode.season_number, Episode.episode_number),
        )
        days = [
            UpcomingDay(day=key, episodes=list(group))
            for key, group in itertools.groupby(coming, key=lambda episode: episode.day)
            if key is not None
        ]
        return Upcoming(new=new, days=days)

    async def up_next(self, user: User, *, now: dt.datetime) -> list[UpcomingEpisode]:
        """Per show in progress, the episode after the last one watched, once aired; most recently active first.

        An episode with no date counts as aired when a later one of its season has.
        """
        last = _last_watched(user)
        candidate = aliased(Episode)
        after_last = sa.or_(
            last.c.season_number.is_(None),
            sa.tuple_(candidate.season_number, candidate.episode_number)
            > sa.tuple_(last.c.season_number, last.c.number),
        )
        following = (
            sa.select(candidate.id)
            .where(candidate.media_id == UserMedia.media_id, candidate.season_number > 0, after_last)
            .order_by(candidate.season_number, candidate.episode_number)
            .limit(1)
            .scalar_subquery()
        )
        later = aliased(Episode)
        later_aired = sa.exists().where(
            later.media_id == Episode.media_id,
            later.season_number == Episode.season_number,
            later.episode_number > Episode.episode_number,
            _air_moment(user.timezone, later) <= now,
        )
        moment = _air_moment(user.timezone)
        return await self._episodes(
            user,
            IN_PROGRESS_STATUSES,
            Episode.id == following,
            sa.or_(moment <= now, sa.and_(moment.is_(None), later_aired)),
            join_last=last,
            order_by=(UserMedia.updated_at.desc(), Media.title),
        )

    async def _episodes(
        self,
        user: User,
        statuses: tuple[TrackingStatus, ...],
        *conditions: sa.ColumnElement[bool],
        order_by: tuple[sa.ColumnExpressionArgument[object], ...],
        join_last: LateralFromClause | None = None,
    ) -> list[UpcomingEpisode]:
        query = (
            sa.select(
                Episode.id,
                Media.tmdb_id,
                Media.title,
                Media.poster_path,
                Episode.season_number,
                Episode.episode_number,
                Episode.title,
                Episode.airstamp,
                _air_day(user.timezone),
            )
            .select_from(UserMedia)
            .join(Media, Media.id == UserMedia.media_id)
        )
        if join_last is not None:
            query = query.outerjoin(join_last, sa.true())
        query = (
            query.join(Episode, Episode.media_id == Media.id)
            .where(UserMedia.user_id == user.id, UserMedia.status.in_(statuses), *conditions)
            .order_by(*order_by)
        )
        return [UpcomingEpisode(*row) for row in await self.session.execute(query)]


def _air_moment(timezone: str, episode: type[Episode] = Episode) -> sa.ColumnElement[dt.datetime]:
    """When an episode airs: its exact airstamp, else the start of its air date in the user's time zone."""
    return sa.func.coalesce(
        episode.airstamp, sa.func.timezone(timezone, sa.cast(episode.air_date, sa.TIMESTAMP(timezone=False)))
    )


def _air_day(timezone: str) -> sa.ColumnElement[dt.date]:
    return sa.cast(sa.func.timezone(timezone, _air_moment(timezone)), sa.Date)


def _watched(user: User, episode: type[Episode]) -> sa.Exists:
    return sa.exists().where(WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id == episode.id)


def _aired_since(user: User, day: sa.ColumnElement[dt.date]) -> sa.ColumnElement[bool]:
    """Whether an episode aired after the user last watched its show: by time when known, else by day."""
    last_watched_at = _last_watched_at(user)
    last_watched_day = sa.cast(sa.func.timezone(user.timezone, last_watched_at), sa.Date)
    return sa.or_(
        Episode.airstamp > last_watched_at,
        sa.and_(Episode.airstamp.is_(None), day >= last_watched_day),
    )


def _last_watched_at(user: User) -> sa.ScalarSelect[dt.datetime]:
    """Per show, when the user last watched one of its episodes."""
    watched = aliased(Episode)
    return (
        sa.select(sa.func.max(WatchedEpisode.watched_at))
        .join(watched, WatchedEpisode.episode_id == watched.id)
        .where(WatchedEpisode.user_id == user.id, watched.media_id == UserMedia.media_id)
        .scalar_subquery()
    )


def _last_watched(user: User) -> LateralFromClause:
    """Per show, the user's furthest watched regular episode in season and episode order."""
    watched = aliased(Episode)
    return (
        sa.select(watched.season_number, watched.episode_number.label("number"))
        .join(WatchedEpisode, WatchedEpisode.episode_id == watched.id)
        .where(WatchedEpisode.user_id == user.id, watched.media_id == UserMedia.media_id, watched.season_number > 0)
        .order_by(watched.season_number.desc(), watched.episode_number.desc())
        .limit(1)
        .lateral("last_watched")
    )
