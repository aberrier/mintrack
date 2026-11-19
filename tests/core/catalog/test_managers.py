import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager, is_stale
from mintrack.core.ratings.managers import RatingManager
from mintrack.core.tracking.managers import ShowTrackingChoice, TrackingManager
from mintrack.db.models import Media, MediaType, Season, TrackingStatus, User, UserMedia
from mintrack.integrations.tmdb.client import TMDBClient
from tests.conftest import cached_media, episodes_of
from tests.fakes.tmdb import DAILY_EPISODES, MAX_ID, FakeTMDB, media_id

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


async def test_the_worker_refreshes_daily_what_a_page_would_and_movies_awaited_on_watch_later(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    refreshed_at = NOW - dt.timedelta(days=2)
    kinds: dict[str, tuple[MediaType, str | None, dt.date | None, dt.date | None, TrackingStatus]] = {
        "airing show": (MediaType.TV, "Returning Series", None, None, TrackingStatus.WATCHING),
        "ended show": (MediaType.TV, "Ended", None, None, TrackingStatus.WATCHING),
        "recent movie": (MediaType.MOVIE, "Released", NOW.date() - dt.timedelta(days=30), None, TrackingStatus.WATCHED),
        "old movie": (MediaType.MOVIE, "Released", dt.date(2001, 1, 1), None, TrackingStatus.WATCHED),
        "undated movie": (MediaType.MOVIE, None, None, None, TrackingStatus.WATCHED),
        "old movie awaited": (MediaType.MOVIE, "Released", dt.date(2001, 1, 1), None, TrackingStatus.WATCH_LATER),
        "old movie out": (
            MediaType.MOVIE,
            "Released",
            dt.date(2001, 1, 1),
            dt.date(2001, 6, 1),
            TrackingStatus.WATCH_LATER,
        ),
    }
    media: dict[str, Media] = {}
    for offset, (name, (media_type, status, released, digital, tracking)) in enumerate(kinds.items(), start=1):
        media[name] = Media(
            media_type=media_type,
            tmdb_id=MAX_ID + 1000 + offset,
            title=name,
            tmdb_status=status,
            release_date=released,
            digital_release_date=digital,
            refreshed_at=refreshed_at,
            language=tmdb.language,
        )
        db_session.add(media[name])
        await db_session.flush()
        db_session.add(
            UserMedia(user_id=user.id, media_id=media[name].id, status=tracking, added_at=NOW, updated_at=NOW)
        )
    await db_session.flush()

    stale = set(await CatalogManager(db_session, tmdb).stale_tracked(NOW))

    by_page = {name for name, item in media.items() if is_stale(item, NOW, tmdb.language)}
    assert by_page == {"airing show", "recent movie", "undated movie"}
    assert {name for name, item in media.items() if item.id in stale} == by_page | {"old movie awaited"}


async def test_a_first_visit_stores_the_show_its_seasons_and_episodes(
    db_session: AsyncSession, tmdb: TMDBClient
) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")

    seasons = await db_session.scalars(sa.select(Season.season_number).where(Season.media_id == show.id))
    assert (show.title, show.tmdb_status, show.tvdb_id) == ("Lighthouse Nights", "Returning Series", show.tmdb_id)
    assert (show.vote_average, show.vote_count) == (8.25, 1234)
    assert sorted(seasons) == [0, 1, 2]
    episodes = await episodes_of(db_session, show)
    assert len(episodes) == 7
    second = episodes[1, 2]
    assert (second.overview, second.still_path, second.vote_average, second.vote_count) == (
        "What happens in episode 2.",
        None,
        7.5,
        24,
    )


async def test_later_visits_read_the_cache(db_session: AsyncSession, tmdb: TMDBClient, fake_tmdb: FakeTMDB) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")
    fake_tmdb.titles[show.tmdb_id] = "Renamed on TMDB"

    again = await CatalogManager(db_session, tmdb).get_or_fetch(MediaType.TV, show.tmdb_id, NOW)

    assert (again.id, again.title) == (show.id, "Lighthouse Nights")


async def test_a_refresh_deletes_dropped_episodes_unless_someone_watched_or_rated_them(
    db_session: AsyncSession, tmdb: TMDBClient, fake_tmdb: FakeTMDB, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")
    episodes = await episodes_of(db_session, show)
    today = dt.datetime.now(dt.UTC)
    await TrackingManager(db_session).mark_episodes(user, show, [episodes[1, 3].id], today, now=today)
    await RatingManager(db_session).rate_episode(user, episodes[2, 1].id, stars=4, review="", now=today)
    fake_tmdb.dropped |= {(show.tmdb_id, 1, 2), (show.tmdb_id, 1, 3), (show.tmdb_id, 2, 1)}

    await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, NOW)

    remaining = await episodes_of(db_session, show)
    assert (1, 2) not in remaining
    assert remaining[1, 3].id == episodes[1, 3].id
    assert remaining[2, 1].id == episodes[2, 1].id
    assert remaining[1, 1].id == episodes[1, 1].id


async def test_shows_with_thousands_of_episodes_are_stored(db_session: AsyncSession, tmdb: TMDBClient) -> None:
    show = await cached_media(db_session, tmdb, "Daily Quiz")

    episodes = await episodes_of(db_session, show)
    assert len(episodes) == DAILY_EPISODES + 4

    await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, NOW)
    assert len(await episodes_of(db_session, show)) == DAILY_EPISODES + 4


async def test_shows_still_airing_go_stale_after_a_day_others_after_a_week() -> None:
    def media(media_type: MediaType, status: str, age: dt.timedelta) -> Media:
        return Media(
            media_type=media_type,
            tmdb_status=status,
            release_date=dt.date(2020, 5, 1),
            refreshed_at=NOW - age,
            language="en",
        )

    hours = dt.timedelta(hours=1)
    assert is_stale(media(MediaType.TV, "Returning Series", 25 * hours), NOW, "en")
    assert not is_stale(media(MediaType.TV, "Returning Series", 23 * hours), NOW, "en")
    assert not is_stale(media(MediaType.TV, "Ended", 6 * 24 * hours), NOW, "en")
    assert is_stale(media(MediaType.TV, "Ended", 8 * 24 * hours), NOW, "en")
    assert not is_stale(media(MediaType.MOVIE, "Released", 6 * 24 * hours), NOW, "en")


async def test_movies_released_in_the_last_six_months_or_not_yet_go_stale_after_a_day() -> None:
    def movie(release_date: dt.date | None) -> Media:
        return Media(
            media_type=MediaType.MOVIE,
            release_date=release_date,
            refreshed_at=NOW - dt.timedelta(hours=25),
            language="en",
        )

    assert is_stale(movie(None), NOW, "en")
    assert is_stale(movie(NOW.date() + dt.timedelta(days=30)), NOW, "en")
    assert is_stale(movie(NOW.date() - dt.timedelta(days=179)), NOW, "en")
    assert not is_stale(movie(NOW.date() - dt.timedelta(days=181)), NOW, "en")


async def test_a_movie_stores_its_first_digital_release_in_any_country(
    db_session: AsyncSession, tmdb: TMDBClient
) -> None:
    await tmdb.search("Digital Dune", MediaType.MOVIE)
    manager = CatalogManager(db_session, tmdb)

    digital = await manager.fetch(MediaType.MOVIE, media_id("movie", "Digital Dune"), NOW)
    theatrical_only = await manager.fetch(MediaType.MOVIE, media_id("movie", "Cinema Only"), NOW)

    assert digital.digital_release_date == dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1)
    assert theatrical_only.digital_release_date is None


async def test_media_fetched_in_another_language_or_an_unknown_one_are_stale_at_once(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Lighthouse Nights")
    await TrackingManager(db_session).set_show_status(user, show, ShowTrackingChoice.WATCHING, NOW)
    manager = CatalogManager(db_session, tmdb)
    just_fetched = show.refreshed_at

    assert show.language == tmdb.language
    assert not is_stale(show, just_fetched, tmdb.language)
    assert show.id not in await manager.stale_tracked(just_fetched)
    for other in ("fr", None):
        show.language = other
        assert is_stale(show, just_fetched, tmdb.language)
        assert show.id in await manager.stale_tracked(just_fetched)


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
