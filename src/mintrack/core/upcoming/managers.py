import collections.abc
import dataclasses
import datetime as dt
import enum
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
# Shows on the watch list, whose new episodes are notified.
IN_PROGRESS_STATUSES = (TrackingStatus.WATCHING, TrackingStatus.UP_TO_DATE, TrackingStatus.NOT_STARTED)
DORMANT_AFTER = dt.timedelta(days=30)


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


class WatchListSection(enum.StrEnum):
    """In this order on the watch list."""

    NEXT = enum.auto()
    # Not watched for DORMANT_AFTER.
    DORMANT = enum.auto()
    # Nothing watched yet: the card is the first regular episode.
    NOT_STARTED = enum.auto()


@dataclasses.dataclass(frozen=True)
class WatchListEpisode(UpcomingEpisode):
    # Aired regular episodes after this one that the user has not watched.
    remaining: int
    last_watched_at: dt.datetime | None
    section: WatchListSection


@dataclasses.dataclass(frozen=True)
class UpcomingDay:
    day: dt.date
    episodes: list[UpcomingEpisode]


@dataclasses.dataclass(frozen=True)
class Upcoming:
    days: list[UpcomingDay]


class UpcomingManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upcoming(self, user: User, *, now: dt.datetime) -> Upcoming:
        """Episodes not watched yet airing from today over the coming weeks, grouped by day in the user's time
        zone. Aired episodes not watched are the watch list's."""
        today = now.astimezone(zoneinfo.ZoneInfo(user.timezone)).date()
        moment, day = _air_moment(user.timezone), _air_day(user.timezone)
        coming = await self._episodes(
            UpcomingEpisode,
            user,
            UserMedia.status.in_(FOLLOWED_STATUSES),
            day.between(today, today + dt.timedelta(days=UPCOMING_DAYS - 1)),
            ~_watched(user, Episode),
            order_by=(moment, Media.title, Episode.season_number, Episode.episode_number),
        )
        days = [
            UpcomingDay(day=key, episodes=list(group))
            for key, group in itertools.groupby(coming, key=lambda episode: episode.day)
            if key is not None
        ]
        return Upcoming(days=days)

    async def watch_list(self, user: User, *, now: dt.datetime, media: Media | None = None) -> list[WatchListEpisode]:
        """Per show in progress (or only `media`), the episode after the last one watched, or the first one of a
        show not started, once aired; by section, most recently watched first, then most recently added.

        An episode with no date counts as aired when a later one of its season has.
        """
        last, last_watch = _last_watched(user), _last_watch(user)
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
        rest = aliased(Episode)
        remaining = (
            sa.select(sa.func.count())
            .where(
                rest.media_id == Episode.media_id,
                rest.season_number > 0,
                sa.tuple_(rest.season_number, rest.episode_number)
                > sa.tuple_(Episode.season_number, Episode.episode_number),
                _air_moment(user.timezone, rest) <= now,
                ~_watched(user, rest),
            )
            .scalar_subquery()
        )
        last_watched_at = last_watch.c.last_watched_at
        sections = list(WatchListSection)
        section = sa.case(
            (UserMedia.status == TrackingStatus.NOT_STARTED, WatchListSection.NOT_STARTED),
            (last_watched_at >= now - DORMANT_AFTER, WatchListSection.NEXT),
            else_=WatchListSection.DORMANT,
        )
        moment = _air_moment(user.timezone)
        return await self._episodes(
            WatchListEpisode,
            user,
            UserMedia.status.in_(IN_PROGRESS_STATUSES),
            UserMedia.media_id == media.id if media is not None else sa.true(),
            Episode.id == following,
            sa.or_(moment <= now, sa.and_(moment.is_(None), later_aired)),
            joins=(last, last_watch),
            columns=(
                remaining,
                last_watched_at,
                sa.type_coerce(
                    section,
                    sa.Enum(WatchListSection, native_enum=False, values_callable=lambda _: [s.value for s in sections]),
                ),
            ),
            order_by=(
                sa.case({value: index for index, value in enumerate(sections)}, value=section),
                last_watched_at.desc().nulls_last(),
                UserMedia.updated_at.desc(),
                Media.title,
            ),
        )

    async def following(self, episode_ids: collections.abc.Collection[uuid.UUID]) -> dict[uuid.UUID, Episode]:
        """Per episode, the regular episode after it in its show, across season ends, aired or not; none after the
        last one."""
        card = aliased(Episode)
        after = (
            sa.select(Episode)
            .where(
                Episode.media_id == card.media_id,
                Episode.season_number > 0,
                sa.tuple_(Episode.season_number, Episode.episode_number)
                > sa.tuple_(card.season_number, card.episode_number),
            )
            .order_by(Episode.season_number, Episode.episode_number)
            .limit(1)
            .correlate(card)
            .lateral("following")
        )
        rows = await self.session.execute(
            sa.select(card.id, aliased(Episode, after)).join(after, sa.true()).where(card.id.in_(episode_ids))
        )
        return dict(rows.all())

    async def _episodes[E: UpcomingEpisode](
        self,
        make: collections.abc.Callable[..., E],
        user: User,
        *conditions: sa.ColumnElement[bool],
        order_by: tuple[sa.ColumnExpressionArgument[object], ...],
        joins: tuple[LateralFromClause, ...] = (),
        columns: tuple[sa.ColumnExpressionArgument[object], ...] = (),
    ) -> list[E]:
        """`make` takes the fields of `UpcomingEpisode`, then the values of `columns`; `joins` are lateral
        subqueries per show of the library."""
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
                *columns,
            )
            .select_from(UserMedia)
            .join(Media, Media.id == UserMedia.media_id)
        )
        for lateral in joins:
            query = query.outerjoin(lateral, sa.true())
        query = (
            query.join(Episode, Episode.media_id == Media.id)
            .where(UserMedia.user_id == user.id, *conditions)
            .order_by(*order_by)
        )
        return [make(*row) for row in await self.session.execute(query)]


def _air_moment(timezone: str, episode: type[Episode] = Episode) -> sa.ColumnElement[dt.datetime]:
    """When an episode airs: its exact airstamp, else the start of its air date in the user's time zone."""
    return sa.func.coalesce(
        episode.airstamp, sa.func.timezone(timezone, sa.cast(episode.air_date, sa.TIMESTAMP(timezone=False)))
    )


def _air_day(timezone: str) -> sa.ColumnElement[dt.date]:
    return sa.cast(sa.func.timezone(timezone, _air_moment(timezone)), sa.Date)


def _watched(user: User, episode: type[Episode]) -> sa.Exists:
    return sa.exists().where(WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id == episode.id)


def _last_watch(user: User) -> LateralFromClause:
    """Per show, when the user last watched one of its episodes (`last_watched_at`)."""
    watched = aliased(Episode)
    return (
        sa.select(sa.func.max(WatchedEpisode.watched_at).label("last_watched_at"))
        .join(watched, WatchedEpisode.episode_id == watched.id)
        .where(WatchedEpisode.user_id == user.id, watched.media_id == UserMedia.media_id)
        .correlate(UserMedia)
        .lateral("last_watch")
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
        .correlate(UserMedia)
        .lateral("last_watched")
    )
