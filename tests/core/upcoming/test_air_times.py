import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.upcoming.air_times import defer_air_times_refreshes, refresh_show_air_times
from mintrack.db.models import Episode, TrackingStatus
from tests.core.upcoming.factories import add_show, add_user, follow
from tests.fakes.tvmaze import FakeTvmaze, tvmaze_episode

FRIDAY = dt.date(2026, 11, 20)
FRIDAY_9PM_NEW_YORK = dt.datetime(2026, 11, 21, 2, tzinfo=dt.UTC)


async def airstamps(session: AsyncSession, episodes: dict[tuple[int, int], Episode]) -> dict[tuple[int, int], object]:
    rows = await session.execute(
        sa.select(Episode.id, Episode.airstamp).where(Episode.id.in_([episode.id for episode in episodes.values()]))
    )
    by_id = dict(rows.all())
    return {key: by_id[episode.id] for key, episode in episodes.items()}


async def test_a_show_gets_tvmaze_air_times_matched_by_season_and_number(db_session: AsyncSession) -> None:
    stale = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    show, episodes = await add_show(
        db_session, {(1, 1): FRIDAY, (1, 2): None, (1, 3): stale, (0, 1): FRIDAY}, tvdb_id=81189
    )
    fake = FakeTvmaze(
        shows={
            81189: (
                169,
                [
                    tvmaze_episode(1, 1, FRIDAY_9PM_NEW_YORK.isoformat()),
                    tvmaze_episode(1, 2, None),
                    {"season": 1, "number": None, "airtime": "20:00", "airstamp": "2026-11-27T01:00:00+00:00"},
                ],
            )
        }
    )

    await refresh_show_air_times(db_session, fake.client(), show)

    assert show.tvmaze_id == 169
    # S01E03 is gone from TVmaze, and specials are never matched: the TMDB date applies.
    assert await airstamps(db_session, episodes) == {
        (1, 1): FRIDAY_9PM_NEW_YORK,
        (1, 2): None,
        (1, 3): None,
        (0, 1): None,
    }


async def test_known_tvmaze_id_skips_the_lookup(db_session: AsyncSession) -> None:
    show, _ = await add_show(db_session, {(1, 1): FRIDAY}, tvdb_id=81189)
    show.tvmaze_id = 169
    fake = FakeTvmaze(shows={81189: (169, [])})

    await refresh_show_air_times(db_session, fake.client(), show)

    assert fake.requests == ["/shows/169/episodes"]


async def test_show_unknown_to_tvmaze_keeps_its_air_times(db_session: AsyncSession) -> None:
    show, episodes = await add_show(db_session, {(1, 1): FRIDAY_9PM_NEW_YORK}, tvdb_id=1)

    await refresh_show_air_times(db_session, FakeTvmaze().client(), show)

    assert show.tvmaze_id is None
    assert await airstamps(db_session, episodes) == {(1, 1): FRIDAY_9PM_NEW_YORK}


async def test_one_job_per_followed_show_still_airing_is_queued_a_second_apart(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    shows = {}
    for title, status, tmdb_status in [
        ("Watching", TrackingStatus.WATCHING, "Returning Series"),
        ("Not Started", TrackingStatus.NOT_STARTED, "Returning Series"),
        ("Later", TrackingStatus.WATCH_LATER, "Returning Series"),
        ("Stopped", TrackingStatus.STOPPED, "Returning Series"),
        ("Ended", TrackingStatus.WATCHING, "Ended"),
    ]:
        shows[title], _ = await add_show(db_session, {(1, 1): FRIDAY}, title=title, tvdb_id=1, tmdb_status=tmdb_status)
        await follow(db_session, user, shows[title], status)
    await add_show(db_session, {(1, 1): FRIDAY}, title="Nobody", tvdb_id=3)

    await defer_air_times_refreshes(db_session)

    queued = await db_session.execute(
        sa.text(
            "SELECT args->>'media_id', lock, scheduled_at FROM procrastinate_jobs "
            "WHERE task_name = 'mintrack:refresh_show_air_times'"
        )
    )
    rows = queued.all()
    expected = {str(shows[title].id) for title in ("Watching", "Not Started", "Later")}
    assert {media_id for media_id, _, _ in rows} == expected
    # Each show's job holds the show's lock, as its refreshes do.
    assert {lock for _, lock, _ in rows} == {f"media:{media_id}" for media_id in expected}
    # The first runs at once, the others a second apart.
    assert sum(scheduled_at is not None for _, _, scheduled_at in rows) == 2
