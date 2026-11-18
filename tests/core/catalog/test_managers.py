import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager, is_stale
from mintrack.core.tracking.managers import ShowTrackingChoice, TrackingManager
from mintrack.db.models import Media, MediaType, Season, User
from mintrack.integrations.tmdb.client import TMDBClient
from tests.conftest import cached_media, episodes_of
from tests.fakes.tmdb import DAILY_EPISODES, FakeTMDB

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


async def test_a_first_visit_stores_the_show_its_seasons_and_episodes(
    db_session: AsyncSession, tmdb: TMDBClient
) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")

    seasons = await db_session.scalars(sa.select(Season.season_number).where(Season.media_id == show.id))
    assert (show.title, show.tmdb_status, show.tvdb_id) == ("Lighthouse Nights", "Returning Series", show.tmdb_id)
    assert sorted(seasons) == [0, 1, 2]
    assert len(await episodes_of(db_session, show)) == 7


async def test_later_visits_read_the_cache(db_session: AsyncSession, tmdb: TMDBClient, fake_tmdb: FakeTMDB) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")
    fake_tmdb.titles[show.tmdb_id] = "Renamed on TMDB"

    again = await CatalogManager(db_session, tmdb).get_or_fetch(MediaType.TV, show.tmdb_id, NOW)

    assert (again.id, again.title) == (show.id, "Lighthouse Nights")


async def test_a_refresh_deletes_dropped_episodes_unless_someone_watched_them(
    db_session: AsyncSession, tmdb: TMDBClient, fake_tmdb: FakeTMDB, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")
    episodes = await episodes_of(db_session, show)
    today = dt.datetime.now(dt.UTC)
    await TrackingManager(db_session).mark_episodes(user, show, [episodes[1, 3].id], today, now=today)
    fake_tmdb.dropped |= {(show.tmdb_id, 1, 2), (show.tmdb_id, 1, 3)}

    await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, NOW)

    remaining = await episodes_of(db_session, show)
    assert (1, 2) not in remaining
    assert remaining[1, 3].id == episodes[1, 3].id
    assert remaining[1, 1].id == episodes[1, 1].id


async def test_shows_with_thousands_of_episodes_are_stored(db_session: AsyncSession, tmdb: TMDBClient) -> None:
    show = await cached_media(db_session, tmdb, "Daily Quiz")

    episodes = await episodes_of(db_session, show)
    assert len(episodes) == DAILY_EPISODES + 4

    await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, NOW)
    assert len(await episodes_of(db_session, show)) == DAILY_EPISODES + 4


async def test_shows_still_airing_go_stale_after_a_day_others_after_a_week() -> None:
    def media(media_type: MediaType, status: str, age: dt.timedelta) -> Media:
        return Media(media_type=media_type, tmdb_status=status, refreshed_at=NOW - age)

    hours = dt.timedelta(hours=1)
    assert is_stale(media(MediaType.TV, "Returning Series", 25 * hours), NOW)
    assert not is_stale(media(MediaType.TV, "Returning Series", 23 * hours), NOW)
    assert not is_stale(media(MediaType.TV, "Ended", 6 * 24 * hours), NOW)
    assert is_stale(media(MediaType.TV, "Ended", 8 * 24 * hours), NOW)
    assert not is_stale(media(MediaType.MOVIE, "Released", 6 * 24 * hours), NOW)


async def test_only_tracked_media_past_their_period_are_refreshed_by_the_worker(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    airing = await cached_media(db_session, tmdb, "Airing Tracked")
    ended = await cached_media(db_session, tmdb, "Ended Tracked")
    await cached_media(db_session, tmdb, "Airing Untracked")
    manager = TrackingManager(db_session)
    for show in (airing, ended):
        await manager.set_show_status(user, show, ShowTrackingChoice.WATCHING, NOW)
    two_days_later = dt.datetime.now(dt.UTC) + dt.timedelta(days=2)

    stale = await CatalogManager(db_session, tmdb).stale_tracked(two_days_later)

    assert airing.id in stale
    assert ended.id not in stale
