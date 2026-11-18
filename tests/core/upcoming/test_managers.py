import collections.abc
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.upcoming.managers import UpcomingEpisode, UpcomingManager
from mintrack.db.models import TrackingStatus
from tests.core.upcoming.factories import add_show, add_user, follow, watch

# Wednesday 18 November 2026, 10:00 in New York.
NOW = dt.datetime(2026, 11, 18, 15, tzinfo=dt.UTC)
TODAY = dt.date(2026, 11, 18)
LAST_WEEK = dt.datetime(2026, 11, 11, 2, tzinfo=dt.UTC)


def labels(episodes: collections.abc.Sequence[UpcomingEpisode]) -> list[str]:
    return [f"{episode.show_title} {episode.season_number}x{episode.episode_number}" for episode in episodes]


async def test_upcoming_groups_followed_shows_by_day_in_the_user_time_zone(db_session: AsyncSession) -> None:
    user = await add_user(db_session, timezone="America/New_York")
    # 02:00 UTC on Thursday is 21:00 on Wednesday in New York.
    tonight = dt.datetime(2026, 11, 19, 2, tzinfo=dt.UTC)
    watching, episodes = await add_show(
        db_session,
        {
            (1, 1): LAST_WEEK,
            (1, 2): tonight,
            (1, 3): dt.date(2026, 11, 25),
            (1, 4): TODAY + dt.timedelta(days=28),
            (1, 5): None,
        },
        title="Watching",
    )
    await follow(db_session, user, watching, TrackingStatus.WATCHING)
    later, _ = await add_show(db_session, {(1, 1): dt.date(2026, 11, 25)}, title="Later")
    await follow(db_session, user, later, TrackingStatus.WATCH_LATER)
    stopped, _ = await add_show(db_session, {(1, 1): tonight}, title="Stopped")
    await follow(db_session, user, stopped, TrackingStatus.STOPPED)
    await add_show(db_session, {(1, 1): tonight}, title="Untracked")
    finished_early, early = await add_show(db_session, {(1, 1): tonight}, title="Seen early")
    await follow(db_session, user, finished_early, TrackingStatus.UP_TO_DATE)
    await watch(db_session, user, early[1, 1], LAST_WEEK)

    upcoming = await UpcomingManager(db_session).upcoming(user, now=NOW)

    assert [(day.day, labels(day.episodes)) for day in upcoming.days] == [
        (TODAY, ["Watching 1x2"]),
        (dt.date(2026, 11, 25), ["Later 1x1", "Watching 1x3"]),
    ]
    tonight_episode = upcoming.days[0].episodes[0]
    assert tonight_episode.airstamp == tonight
    assert tonight_episode.episode_id == episodes[1, 2].id
    assert upcoming.days[1].episodes[0].airstamp is None


async def test_upcoming_lists_nothing_aired_before_today(db_session: AsyncSession) -> None:
    user = await add_user(db_session, timezone="America/New_York")
    show, episodes = await add_show(
        db_session,
        {(1, 1): dt.datetime(2012, 3, 1, 2, tzinfo=dt.UTC), (1, 2): LAST_WEEK, (1, 3): NOW},
        title="Show",
    )
    await follow(db_session, user, show, TrackingStatus.WATCHING)
    await watch(db_session, user, episodes[1, 1], LAST_WEEK - dt.timedelta(days=1))

    upcoming = await UpcomingManager(db_session).upcoming(user, now=NOW)

    assert [(day.day, labels(day.episodes)) for day in upcoming.days] == [(TODAY, ["Show 1x3"])]


async def test_upcoming_lists_only_the_user_own_shows_and_watches(db_session: AsyncSession) -> None:
    user, other = await add_user(db_session), await add_user(db_session)
    tonight = dt.datetime(2026, 11, 19, 2, tzinfo=dt.UTC)
    shared, episodes = await add_show(db_session, {(1, 1): tonight}, title="Shared")
    theirs, _ = await add_show(db_session, {(1, 1): tonight}, title="Theirs")
    for follower in (user, other):
        await follow(db_session, follower, shared, TrackingStatus.WATCHING)
    await follow(db_session, other, theirs, TrackingStatus.WATCHING)
    # Seen early by the other user only.
    await watch(db_session, other, episodes[1, 1], LAST_WEEK)

    mine = await UpcomingManager(db_session).upcoming(user, now=NOW)
    others = await UpcomingManager(db_session).upcoming(other, now=NOW)

    assert [labels(day.episodes) for day in mine.days] == [["Shared 1x1"]]
    assert [labels(day.episodes) for day in others.days] == [["Theirs 1x1"]]


async def test_the_watch_list_is_the_aired_episode_after_the_last_one_watched(db_session: AsyncSession) -> None:
    user = await add_user(db_session, timezone="America/New_York")
    future = NOW + dt.timedelta(days=2)

    started, started_episodes = await add_show(
        db_session, {(1, 1): LAST_WEEK, (1, 2): LAST_WEEK, (2, 1): LAST_WEEK}, title="Started"
    )
    await follow(db_session, user, started, TrackingStatus.WATCHING)
    await watch(db_session, user, started_episodes[1, 2], LAST_WEEK)

    caught_up, caught_up_episodes = await add_show(db_session, {(1, 1): LAST_WEEK, (1, 2): future}, title="Caught up")
    await follow(db_session, user, caught_up, TrackingStatus.UP_TO_DATE)
    await watch(db_session, user, caught_up_episodes[1, 1], LAST_WEEK)

    new, _ = await add_show(db_session, {(0, 1): LAST_WEEK, (1, 1): dt.date(2026, 11, 18)}, title="New")
    await follow(db_session, user, new, TrackingStatus.WATCHING)

    undated, undated_episodes = await add_show(
        db_session, {(1, 1): LAST_WEEK, (1, 2): None, (1, 3): LAST_WEEK, (2, 1): None}, title="Undated"
    )
    await follow(db_session, user, undated, TrackingStatus.WATCHING)
    await watch(db_session, user, undated_episodes[1, 1], LAST_WEEK)

    later, _ = await add_show(db_session, {(1, 1): LAST_WEEK}, title="Later")
    await follow(db_session, user, later, TrackingStatus.WATCH_LATER)

    up_next = await UpcomingManager(db_session).watch_list(user, now=NOW)

    # Most recently watched first, never watched last; an undated episode counts as aired when a later one of its
    # season has.
    assert labels(up_next) == ["Undated 1x2", "Started 2x1", "New 1x1"]
    assert up_next[2].day == TODAY


async def test_the_watch_list_waits_for_an_undated_episode_with_nothing_aired_after_it(
    db_session: AsyncSession,
) -> None:
    user = await add_user(db_session)
    show, episodes = await add_show(db_session, {(1, 1): LAST_WEEK, (2, 1): None, (2, 2): None}, title="Show")
    await follow(db_session, user, show, TrackingStatus.WATCHING)
    await watch(db_session, user, episodes[1, 1], LAST_WEEK)

    assert await UpcomingManager(db_session).watch_list(user, now=NOW) == []
