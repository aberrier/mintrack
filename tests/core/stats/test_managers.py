import datetime as dt
import itertools

from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.stats.managers import MonthCount, Ranked, StatsManager
from mintrack.db.models import Media, MediaType, TrackingStatus, User, WatchedMovie
from tests.core.upcoming.factories import add_show, add_user, follow, watch
from tests.fakes.tmdb import MAX_ID

NOW = dt.datetime(2026, 11, 18, 15, tzinfo=dt.UTC)
_movie_ids = itertools.count(MAX_ID + 1)


async def add_movie(session: AsyncSession, title: str, runtime: int | None, genres: list[str]) -> Media:
    movie = Media(
        media_type=MediaType.MOVIE,
        tmdb_id=next(_movie_ids),
        title=title,
        runtime=runtime,
        genres=genres,
        refreshed_at=NOW,
    )
    session.add(movie)
    await session.flush()
    return movie


async def watch_movie(session: AsyncSession, user: User, movie: Media, at: dt.datetime) -> None:
    session.add(WatchedMovie(user_id=user.id, media_id=movie.id, watched_at=at))
    await session.flush()


async def test_totals_and_minutes_count_each_episode_by_its_runtime_or_its_shows_average(
    db_session: AsyncSession,
) -> None:
    user = await add_user(db_session)
    dark, dark_episodes = await add_show(db_session, {(0, 1): None, (1, 1): None, (1, 2): None}, title="Dark")
    dark.network, dark.genres = "Netflix", ["Drama", "Mystery"]
    dark_episodes[1, 1].runtime, dark_episodes[1, 2].runtime = 50, 60
    quiet, quiet_episodes = await add_show(db_session, {(1, 1): None}, title="Quiet")
    quiet.network, quiet.genres = "HBO", ["Drama"]
    aside, _ = await add_show(db_session, {(1, 1): None}, title="Aside")
    await follow(db_session, user, dark, TrackingStatus.FINISHED)
    await follow(db_session, user, quiet, TrackingStatus.WATCHING)
    await follow(db_session, user, aside, TrackingStatus.WATCH_LATER)
    for episode in [*dark_episodes.values(), quiet_episodes[1, 1]]:
        await watch(db_session, user, episode, NOW)
    await watch_movie(db_session, user, await add_movie(db_session, "Heat", 170, ["Action", "Crime"]), NOW)
    await watch_movie(db_session, user, await add_movie(db_session, "Untimed", None, []), NOW)
    # Another user's watches are theirs: an episode of the same show they follow too, another show and a movie, with
    # their own genre and network.
    other = await add_user(db_session)
    await follow(db_session, other, dark, TrackingStatus.WATCHING)
    await watch(db_session, other, dark_episodes[1, 1], NOW)
    gloom, gloom_episodes = await add_show(db_session, {(1, 1): None}, title="Gloom")
    gloom.network, gloom.genres = "BBC", ["Horror"]
    await follow(db_session, other, gloom, TrackingStatus.FINISHED)
    await watch(db_session, other, gloom_episodes[1, 1], NOW)
    await watch_movie(db_session, other, await add_movie(db_session, "Fright", 90, ["Horror"]), NOW)

    stats = await StatsManager(db_session).statistics(user, NOW)

    # Aside has nothing watched, so it is not counted among the shows, as movies only count those watched.
    assert (stats.episodes, stats.movies, stats.shows, stats.finished_shows) == (4, 2, 2, 1)
    # The special without a runtime counts Dark's average, 55; Quiet has none at all.
    assert (stats.episode_minutes, stats.episodes_without_runtime) == (50 + 60 + 55, 1)
    assert (stats.movie_minutes, stats.movies_without_runtime) == (170, 1)
    assert stats.genres == [Ranked("Drama", 2), Ranked("Action", 1), Ranked("Crime", 1), Ranked("Mystery", 1)]
    assert stats.networks == [Ranked("HBO", 1), Ranked("Netflix", 1)]


async def test_an_average_runtime_counts_to_the_nearest_minute(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    show, episodes = await add_show(db_session, {(1, 1): None, (1, 2): None, (1, 3): None})
    episodes[1, 1].runtime, episodes[1, 2].runtime = 45, 50
    await follow(db_session, user, show, TrackingStatus.WATCHING)
    await watch(db_session, user, episodes[1, 3], NOW)

    stats = await StatsManager(db_session).statistics(user, NOW)

    # The show's average is 47.5 minutes.
    assert stats.episode_minutes == 48


async def test_months_and_streaks_follow_the_users_time_zone(db_session: AsyncSession) -> None:
    user = await add_user(db_session, timezone="Europe/Paris")
    show, episodes = await add_show(db_session, {(1, number): None for number in range(1, 11)})
    movie = await add_movie(db_session, "Heat", 170, [])
    watches = [
        # 23:00 on November 30 in Paris: before the twelve months.
        dt.datetime(2025, 11, 30, 22, tzinfo=dt.UTC),
        # 00:30 on December 1 in Paris.
        dt.datetime(2025, 11, 30, 23, 30, tzinfo=dt.UTC),
        dt.datetime(2026, 3, 1, 12, tzinfo=dt.UTC),
        dt.datetime(2026, 3, 3, 12, tzinfo=dt.UTC),
        dt.datetime(2026, 3, 4, 12, tzinfo=dt.UTC),
        dt.datetime(2026, 11, 16, 12, tzinfo=dt.UTC),
        dt.datetime(2026, 11, 17, 12, tzinfo=dt.UTC),
        # Today, November 18, in Paris.
        dt.datetime(2026, 11, 17, 23, 30, tzinfo=dt.UTC),
    ]
    await follow(db_session, user, show, TrackingStatus.WATCHING)
    for number, at in enumerate(watches, start=1):
        await watch(db_session, user, episodes[1, number], at)
    await watch_movie(db_session, user, movie, dt.datetime(2026, 3, 2, 12, tzinfo=dt.UTC))

    manager = StatsManager(db_session)
    stats = await manager.statistics(user, NOW)
    tomorrow = await manager.statistics(user, NOW + dt.timedelta(days=1))
    later = await manager.statistics(user, NOW + dt.timedelta(days=2))

    assert len(stats.months) == 12
    assert stats.months[0] == MonthCount(dt.date(2025, 12, 1), 1, 0)
    assert stats.months[3] == MonthCount(dt.date(2026, 3, 1), 3, 1)
    assert stats.months[-1] == MonthCount(dt.date(2026, 11, 1), 3, 0)
    assert sum(month.episodes + month.movies for month in stats.months) == 8
    # March 1 to 4, the movie included.
    assert (stats.current_streak, stats.longest_streak) == (3, 4)
    # A streak lasts until a whole day passes without a watch.
    assert (tomorrow.current_streak, later.current_streak) == (3, 0)


async def test_a_user_who_watched_nothing_gets_zeros(db_session: AsyncSession) -> None:
    stats = await StatsManager(db_session).statistics(await add_user(db_session), NOW)

    assert (stats.episodes, stats.movies, stats.shows, stats.episode_minutes, stats.movie_minutes) == (0, 0, 0, 0, 0)
    assert (stats.current_streak, stats.longest_streak, stats.genres, stats.networks) == (0, 0, [], [])
    assert [month.month for month in stats.months][:2] == [dt.date(2025, 12, 1), dt.date(2026, 1, 1)]
    assert not any(month.episodes or month.movies for month in stats.months)
