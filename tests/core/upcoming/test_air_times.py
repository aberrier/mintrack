import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.upcoming import air_times
from mintrack.core.upcoming.air_times import refresh_air_times
from mintrack.db.models import Episode, TrackingStatus
from tests.core.upcoming.factories import add_show, add_user, follow
from tests.fakes.tvmaze import FakeTvmaze, tvmaze_episode

FRIDAY = dt.date(2026, 11, 20)
FRIDAY_9PM_NEW_YORK = dt.datetime(2026, 11, 21, 2, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def no_pause_between_shows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(air_times, "SECONDS_BETWEEN_SHOWS", 0)


async def airstamps(session: AsyncSession, episodes: dict[tuple[int, int], Episode]) -> dict[tuple[int, int], object]:
    rows = await session.execute(
        sa.select(Episode.id, Episode.airstamp).where(Episode.id.in_([episode.id for episode in episodes.values()]))
    )
    by_id = dict(rows.all())
    return {key: by_id[episode.id] for key, episode in episodes.items()}


async def test_followed_show_gets_tvmaze_air_times_matched_by_season_and_number(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    stale = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    show, episodes = await add_show(
        db_session, {(1, 1): FRIDAY, (1, 2): None, (1, 3): stale, (0, 1): FRIDAY}, tvdb_id=81189
    )
    await follow(db_session, user, show, TrackingStatus.WATCHING)
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

    await refresh_air_times(db_session, fake.client())

    assert show.tvmaze_id == 169
    # S01E03 is gone from TVmaze, and specials are never matched: the TMDB date applies.
    assert await airstamps(db_session, episodes) == {
        (1, 1): FRIDAY_9PM_NEW_YORK,
        (1, 2): None,
        (1, 3): None,
        (0, 1): None,
    }


async def test_known_tvmaze_id_skips_the_lookup(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    show, _ = await add_show(db_session, {(1, 1): FRIDAY}, tvdb_id=81189)
    show.tvmaze_id = 169
    await follow(db_session, user, show, TrackingStatus.UP_TO_DATE)
    fake = FakeTvmaze(shows={81189: (169, [])})

    await refresh_air_times(db_session, fake.client())

    assert fake.requests == ["/shows/169/episodes"]


async def test_show_unknown_to_tvmaze_keeps_its_air_times(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    show, episodes = await add_show(db_session, {(1, 1): FRIDAY_9PM_NEW_YORK}, tvdb_id=1)
    await follow(db_session, user, show, TrackingStatus.WATCH_LATER)

    await refresh_air_times(db_session, FakeTvmaze().client())

    assert show.tvmaze_id is None
    assert await airstamps(db_session, episodes) == {(1, 1): FRIDAY_9PM_NEW_YORK}


async def test_only_followed_shows_still_airing_are_refreshed(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    stopped, _ = await add_show(db_session, {(1, 1): FRIDAY}, title="Stopped", tvdb_id=1)
    await follow(db_session, user, stopped, TrackingStatus.STOPPED)
    ended, _ = await add_show(db_session, {(1, 1): FRIDAY}, title="Ended", tvdb_id=2, tmdb_status="Ended")
    await follow(db_session, user, ended, TrackingStatus.WATCHING)
    await add_show(db_session, {(1, 1): FRIDAY}, title="Nobody", tvdb_id=3)
    fake = FakeTvmaze(shows={1: (11, []), 2: (12, []), 3: (13, [])})

    await refresh_air_times(db_session, fake.client())

    assert fake.requests == []


async def test_a_failing_show_does_not_stop_the_others(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    failing, _ = await add_show(db_session, {(1, 1): FRIDAY}, title="Failing", tvdb_id=1)
    working, episodes = await add_show(db_session, {(1, 1): FRIDAY}, title="Working", tvdb_id=2)
    for show in (failing, working):
        await follow(db_session, user, show, TrackingStatus.WATCHING)
    fake = FakeTvmaze(
        shows={1: (11, []), 2: (12, [tvmaze_episode(1, 1, FRIDAY_9PM_NEW_YORK.isoformat())])}, failing={11}
    )

    await refresh_air_times(db_session, fake.client())

    assert failing.tvmaze_id is None
    assert await airstamps(db_session, episodes) == {(1, 1): FRIDAY_9PM_NEW_YORK}
