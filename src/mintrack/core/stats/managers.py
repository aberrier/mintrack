import dataclasses
import datetime as dt
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Episode, Media, TrackingStatus, User, UserMedia, WatchedEpisode, WatchedMovie

MONTHS = 12
TOP = 5


@dataclasses.dataclass(frozen=True)
class MonthCount:
    # The first day of the month, in the user's time zone.
    month: dt.date
    episodes: int
    movies: int


@dataclasses.dataclass(frozen=True)
class Ranked:
    name: str
    # Shows with a watched episode, and watched movies.
    titles: int


@dataclasses.dataclass(frozen=True)
class Statistics:
    episodes: int
    movies: int
    # Shows with a watched episode, as movies count those watched, and those of them finished.
    shows: int
    finished_shows: int
    episode_minutes: int
    movie_minutes: int
    # Watches left out of the minutes: TMDB gives no runtime for the movie, nor for any episode of the show.
    episodes_without_runtime: int
    movies_without_runtime: int
    # The last MONTHS months, oldest first, this one included.
    months: list[MonthCount]
    # Consecutive days with a watch, in the user's time zone; the current streak lasts until a whole day passes
    # without one.
    current_streak: int
    longest_streak: int
    genres: list[Ranked]
    networks: list[Ranked]


class StatsManager:
    """A user's own figures, computed by PostgreSQL from their watches."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def statistics(self, user: User, now: dt.datetime) -> Statistics:
        today = now.astimezone(zoneinfo.ZoneInfo(user.timezone)).date()
        episodes, episode_minutes, episodes_without_runtime = await self._episodes(user)
        movies, movie_minutes, movies_without_runtime = (
            await self.session.execute(
                sa.select(
                    sa.func.count(), _total_minutes(Media.runtime), sa.func.count().filter(Media.runtime.is_(None))
                )
                .select_from(WatchedMovie)
                .join(Media, Media.id == WatchedMovie.media_id)
                .where(WatchedMovie.user_id == user.id)
            )
        ).one()
        shows, finished_shows = (
            await self.session.execute(
                sa.select(sa.func.count(), sa.func.count().filter(UserMedia.status == TrackingStatus.FINISHED))
                .select_from(UserMedia)
                .where(UserMedia.user_id == user.id, UserMedia.media_id.in_(_watched_shows(user)))
            )
        ).one()
        current_streak, longest_streak = await self._streaks(user, today)
        return Statistics(
            episodes=episodes,
            movies=movies,
            shows=shows,
            finished_shows=finished_shows,
            episode_minutes=episode_minutes,
            movie_minutes=movie_minutes,
            episodes_without_runtime=episodes_without_runtime,
            movies_without_runtime=movies_without_runtime,
            months=await self._months(user, today),
            current_streak=current_streak,
            longest_streak=longest_streak,
            genres=await self._genres(user),
            networks=await self._networks(user),
        )

    async def _episodes(self, user: User) -> sa.Row[int, int, int]:
        """Watched episodes, their minutes and those without a runtime. An episode without one counts the average
        runtime of its show's other episodes."""
        show_runtimes = (
            sa.select(Episode.media_id, sa.func.avg(Episode.runtime).label("runtime"))
            .where(Episode.media_id.in_(sa.select(UserMedia.media_id).where(UserMedia.user_id == user.id)))
            .group_by(Episode.media_id)
            .subquery()
        )
        minutes = sa.func.coalesce(Episode.runtime, show_runtimes.c.runtime)
        return (
            await self.session.execute(
                sa.select(sa.func.count(), _total_minutes(minutes), sa.func.count().filter(minutes.is_(None)))
                .select_from(WatchedEpisode)
                .join(Episode, Episode.id == WatchedEpisode.episode_id)
                .outerjoin(show_runtimes, show_runtimes.c.media_id == Episode.media_id)
                .where(WatchedEpisode.user_id == user.id)
            )
        ).one()

    async def _months(self, user: User, today: dt.date) -> list[MonthCount]:
        months = [_add_months(today.replace(day=1), offset) for offset in range(1 - MONTHS, 1)]
        watches = _watches(user, since=dt.datetime.combine(months[0], dt.time(), zoneinfo.ZoneInfo(user.timezone)))
        month = sa.cast(sa.func.date_trunc("month", _local(user, watches.c.watched_at)), sa.Date)
        rows = await self.session.execute(
            sa.select(
                month, sa.func.count().filter(~watches.c.movie), sa.func.count().filter(watches.c.movie)
            ).group_by(month)
        )
        counts = {first_day: (episodes, movies) for first_day, episodes, movies in rows}
        return [MonthCount(first_day, *counts.get(first_day, (0, 0))) for first_day in months]

    async def _streaks(self, user: User, today: dt.date) -> tuple[int, int]:
        """The current and the longest streak, from the runs of consecutive days the database finds."""
        watches = _watches(user)
        days = sa.select(sa.cast(_local(user, watches.c.watched_at), sa.Date).label("day")).distinct().subquery()
        # Consecutive days minus their rank give the same date: one per run.
        run = days.c.day - sa.cast(sa.func.row_number().over(order_by=days.c.day), sa.Integer)
        runs = sa.select(days.c.day, run.label("run")).subquery()
        rows = (
            await self.session.execute(sa.select(sa.func.max(runs.c.day), sa.func.count()).group_by(runs.c.run))
        ).all()
        yesterday = today - dt.timedelta(days=1)
        current = next((length for last_day, length in rows if last_day >= yesterday), 0)
        return current, max((length for _, length in rows), default=0)

    async def _genres(self, user: User) -> list[Ranked]:
        watched = sa.union(
            _watched_shows(user), sa.select(WatchedMovie.media_id).where(WatchedMovie.user_id == user.id)
        )
        genres = (
            sa.select(sa.func.unnest(Media.genres, type_=sa.Text).label("name")).where(
                Media.id.in_(watched.scalar_subquery())
            )
        ).subquery()
        return await self._ranked(genres.c.name)

    async def _networks(self, user: User) -> list[Ranked]:
        return await self._ranked(Media.network, Media.id.in_(_watched_shows(user)), Media.network.is_not(None))

    async def _ranked(
        self, name: sa.SQLColumnExpression[str | None], *criteria: sa.SQLColumnExpression[bool]
    ) -> list[Ranked]:
        """The TOP names of most titles, then alphabetically."""
        titles = sa.func.count()
        rows = await self.session.execute(
            sa.select(name, titles).where(*criteria).group_by(name).order_by(titles.desc(), name).limit(TOP)
        )
        return [Ranked(name, count) for name, count in rows if name is not None]


def _watches(user: User, *, since: dt.datetime | None = None) -> sa.Subquery:
    """When the user watched each episode and movie, and whether it was a movie, read from their (user, watched at)
    indexes."""
    episodes = sa.select(WatchedEpisode.watched_at, sa.false().label("movie")).where(WatchedEpisode.user_id == user.id)
    movies = sa.select(WatchedMovie.watched_at, sa.true().label("movie")).where(WatchedMovie.user_id == user.id)
    if since is not None:
        episodes = episodes.where(WatchedEpisode.watched_at >= since)
        movies = movies.where(WatchedMovie.watched_at >= since)
    return sa.union_all(episodes, movies).subquery()


def _total_minutes(runtime: sa.SQLColumnExpression[int | None]) -> sa.ColumnElement[int]:
    return sa.cast(sa.func.round(sa.func.coalesce(sa.func.sum(runtime), 0)), sa.Integer)


def _watched_shows(user: User) -> sa.Select[uuid.UUID]:
    return (
        sa.select(Episode.media_id)
        .join(WatchedEpisode, WatchedEpisode.episode_id == Episode.id)
        .where(WatchedEpisode.user_id == user.id)
    )


def _local(user: User, instant: sa.ColumnElement[dt.datetime]) -> sa.ColumnElement[dt.datetime]:
    """The wall-clock time in the user's time zone."""
    return sa.func.timezone(user.timezone, instant)


def _add_months(first_day: dt.date, months: int) -> dt.date:
    year, month = divmod(first_day.year * 12 + first_day.month - 1 + months, 12)
    return dt.date(year, month + 1, 1)
