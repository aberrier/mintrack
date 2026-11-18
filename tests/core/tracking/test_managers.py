import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import TrackingManager, UnknownEpisodesError
from mintrack.db.models import Episode, MediaType, TrackingStatus, User
from mintrack.integrations.tmdb.client import TMDBClient
from tests.conftest import cached_media, episodes_of


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def aired_regular(episodes: dict[tuple[int, int], Episode]) -> list[Episode]:
    """The fake show's aired episodes: all but S02E03, which airs in a week (specials excluded)."""
    return [episode for key, episode in episodes.items() if key[0] != 0 and key != (2, 3)]


async def test_one_tap_marks_an_episode_at_the_tap_time_and_another_unmarks_it(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Tap Twice")
    episode = (await episodes_of(db_session, show))[1, 1]
    manager, tapped_at = TrackingManager(db_session), now()

    marked = await manager.mark_watched(user, episode, tapped_at)
    again = await manager.mark_watched(user, episode, tapped_at + dt.timedelta(minutes=5))
    unmarked = await manager.unmark_watched(user, episode, now())

    assert marked.watched == {episode.id: tapped_at}
    assert again.watched == {episode.id: tapped_at}
    assert marked.status is TrackingStatus.WATCHING
    assert unmarked is not None
    assert unmarked.watched == {}
    assert unmarked.status is TrackingStatus.WATCH_LATER


async def test_statuses_follow_progress(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    manager = TrackingManager(db_session)
    airing = await cached_media(db_session, tmdb, "Still Airing")
    ended = await cached_media(db_session, tmdb, "Ended Already")

    added = await manager.track_show(user, airing, stopped=False, now=now())
    caught_up = await manager.mark_episodes(
        user, airing, [e.id for e in aired_regular(await episodes_of(db_session, airing))], now()
    )
    finished = await manager.mark_episodes(
        user, ended, [e.id for k, e in (await episodes_of(db_session, ended)).items() if k[0] != 0], now()
    )

    assert added.status is TrackingStatus.WATCH_LATER
    assert caught_up.status is TrackingStatus.UP_TO_DATE
    assert finished.status is TrackingStatus.FINISHED


async def test_episodes_without_a_date_do_not_keep_an_ended_show_from_finishing(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Undated Ended")
    show.tmdb_status = "Ended"
    dated = [e.id for (season, _), e in (await episodes_of(db_session, show)).items() if season != 0 and e.air_date]

    manager = TrackingManager(db_session)
    undated = next(e.id for (season, _), e in (await episodes_of(db_session, show)).items() if not e.air_date)

    tracking = await manager.mark_episodes(user, show, [*dated, undated], now())

    item = next(item for item in await manager.library(user, MediaType.TV, now()) if item.media.id == show.id)
    assert tracking.status is TrackingStatus.FINISHED
    # The library counts aired episodes only, so marking one without a date never shows more watched than aired.
    assert (item.watched_count, item.aired_count) == (5, 5)


async def test_marking_with_a_past_date_keeps_the_latest_activity_for_the_library(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Imported Show")
    episodes = await episodes_of(db_session, show)
    manager, today = TrackingManager(db_session), now()
    await manager.mark_watched(user, episodes[1, 2], today)

    await manager.mark_watched(user, episodes[1, 1], today - dt.timedelta(days=400))

    item = next(item for item in await manager.library(user, MediaType.TV, now()) if item.media.id == show.id)
    assert item.updated_at == today
    tracking = await manager.show_tracking(user, show)
    assert tracking is not None
    assert tracking.watched[episodes[1, 1].id] == today - dt.timedelta(days=400)


async def test_a_stopped_show_stays_stopped_until_an_episode_is_marked(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Paused Drama")
    episodes = await episodes_of(db_session, show)
    manager = TrackingManager(db_session)
    await manager.mark_watched(user, episodes[1, 1], now())
    await manager.mark_watched(user, episodes[1, 2], now())

    stopped = await manager.track_show(user, show, stopped=True, now=now())
    still_stopped = await manager.unmark_watched(user, episodes[1, 2], now())
    back = await manager.mark_watched(user, episodes[1, 2], now())

    assert stopped.status is TrackingStatus.STOPPED
    assert still_stopped is not None
    assert still_stopped.status is TrackingStatus.STOPPED
    assert back.status is TrackingStatus.WATCHING


async def test_a_show_put_aside_stays_there_until_an_episode_is_marked_or_it_is_resumed(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Aside Drama")
    episodes = await episodes_of(db_session, show)
    manager = TrackingManager(db_session)
    await manager.mark_watched(user, episodes[1, 1], now())

    aside = await manager.watch_later(user, show, now())
    back = await manager.mark_watched(user, episodes[1, 2], now())
    await manager.watch_later(user, show, now())
    resumed = await manager.track_show(user, show, stopped=False, now=now())

    assert aside.status is TrackingStatus.WATCH_LATER
    assert back.status is TrackingStatus.WATCHING
    assert resumed.status is TrackingStatus.WATCHING


async def test_episodes_of_another_show_are_refused(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    show = await cached_media(db_session, tmdb, "Mine")
    other = await cached_media(db_session, tmdb, "Other")
    foreign = (await episodes_of(db_session, other))[1, 1]

    with pytest.raises(UnknownEpisodesError):
        await TrackingManager(db_session).mark_episodes(user, show, [foreign.id], now())


async def test_movies_are_watched_or_to_watch_later(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    movie = await cached_media(db_session, tmdb, "Paper Moons", MediaType.MOVIE)
    manager, watched_at = TrackingManager(db_session), now()

    later = await manager.set_movie_watched(user, movie, watched=False, now=watched_at)
    watched = await manager.set_movie_watched(user, movie, watched=True, now=watched_at)

    assert (later.status, later.watched_at) == (TrackingStatus.WATCH_LATER, None)
    assert (watched.status, watched.watched_at) == (TrackingStatus.WATCHED, watched_at)


async def test_removing_a_show_forgets_what_was_watched(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    show = await cached_media(db_session, tmdb, "Gone Soon")
    manager = TrackingManager(db_session)
    await manager.mark_watched(user, (await episodes_of(db_session, show))[1, 1], now())

    await manager.untrack(user, show)

    assert await manager.show_tracking(user, show) is None
    assert (await manager.track_show(user, show, stopped=False, now=now())).watched == {}


async def test_the_library_counts_aired_and_watched_regular_episodes(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Counted Show")
    episodes = await episodes_of(db_session, show)
    manager = TrackingManager(db_session)
    await manager.mark_episodes(user, show, [episodes[0, 1].id, episodes[1, 1].id, episodes[1, 2].id], now())

    items = {item.media.id: item for item in await manager.library(user, MediaType.TV, now())}

    assert (items[show.id].watched_count, items[show.id].aired_count) == (2, 5)
    assert items[show.id].status is TrackingStatus.WATCHING


async def test_a_refresh_updates_the_status_of_everyone_tracking_the_show(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Refreshed Show")
    manager = TrackingManager(db_session)
    await manager.mark_episodes(user, show, [e.id for e in aired_regular(await episodes_of(db_session, show))], now())

    # Eight days later, the last episode has aired.
    await manager.refresh_statuses(show, now() + dt.timedelta(days=8))

    tracking = await manager.show_tracking(user, show)
    assert tracking is not None
    assert tracking.status is TrackingStatus.WATCHING
    show = await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, now())
    assert show.title == "Refreshed Show"
