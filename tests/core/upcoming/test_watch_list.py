import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.upcoming.managers import UpcomingManager, WatchListSection
from mintrack.db.models import TrackingStatus
from tests.core.upcoming.factories import add_show, add_user, follow, watch

NOW = dt.datetime(2026, 11, 18, 15, tzinfo=dt.UTC)
LAST_WEEK = NOW - dt.timedelta(days=7)


async def test_the_watch_list_counts_what_remains_and_splits_by_last_watch(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    recent, recent_episodes = await add_show(
        db_session,
        {
            (0, 1): LAST_WEEK,
            (1, 1): LAST_WEEK,
            (1, 2): LAST_WEEK,
            (1, 3): LAST_WEEK,
            (1, 4): LAST_WEEK,
            (2, 1): NOW + dt.timedelta(days=1),
        },
        title="Recent",
    )
    old, old_episodes = await add_show(db_session, {(1, 1): LAST_WEEK, (1, 2): LAST_WEEK}, title="Old")
    lately, lately_episodes = await add_show(db_session, {(1, 1): LAST_WEEK, (1, 2): LAST_WEEK}, title="Lately")
    # Followed in this order, so the most recently followed is not the most recently watched.
    for show in (recent, lately, old):
        await follow(db_session, user, show, TrackingStatus.WATCHING)
    await watch(db_session, user, recent_episodes[1, 1], NOW - dt.timedelta(days=2))
    await watch(db_session, user, lately_episodes[1, 1], NOW - dt.timedelta(days=29))
    await watch(db_session, user, old_episodes[1, 1], NOW - dt.timedelta(days=31))

    watch_list = await UpcomingManager(db_session).up_next(user, now=NOW)

    # Specials and episodes still to air are not counted.
    assert [
        (episode.show_title, episode.episode_number, episode.remaining, episode.section) for episode in watch_list
    ] == [
        ("Recent", 2, 2, WatchListSection.NEXT),
        ("Lately", 2, 0, WatchListSection.NEXT),
        ("Old", 2, 0, WatchListSection.DORMANT),
    ]
    assert watch_list[0].last_watched_at == NOW - dt.timedelta(days=2)
