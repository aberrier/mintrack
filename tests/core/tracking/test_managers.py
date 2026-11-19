import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import (
    MIN_WATCH_DATE,
    FutureWatchError,
    SeasonSummary,
    ShowTrackingChoice,
    TrackingManager,
    UnairedEpisodesError,
    UnknownEpisodesError,
    earliest_watch,
)
from mintrack.db.models import Episode, MediaType, TrackingStatus, User
from mintrack.integrations.tmdb.client import TMDBClient
from tests.conftest import cached_media, episodes_of
from tests.core.upcoming.factories import add_show, add_user


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def test_a_watch_is_dated_at_the_earliest_the_day_before_the_air_date_or_in_1900() -> None:
    aired = Episode(air_date=dt.date(2026, 3, 10))
    undated = Episode(air_date=None)

    assert earliest_watch(aired) == dt.datetime(2026, 3, 9, tzinfo=dt.UTC)
    assert earliest_watch(undated) == MIN_WATCH_DATE == dt.datetime(1900, 1, 1, tzinfo=dt.UTC)


def aired_regular(episodes: dict[tuple[int, int], Episode]) -> list[Episode]:
    """The fake show's aired episodes: all but S02E03, which airs in a week (specials excluded)."""
    return [episode for key, episode in episodes.items() if key[0] != 0 and key != (2, 3)]


async def test_one_tap_marks_an_episode_at_the_tap_time_and_another_unmarks_it(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Tap Twice")
    episode = (await episodes_of(db_session, show))[1, 1]
    manager, tapped_at = TrackingManager(db_session), now()

    marked = await manager.mark_episodes(user, show, [episode.id], tapped_at, now=tapped_at)
    again = await manager.mark_episodes(
        user, show, [episode.id], tapped_at + dt.timedelta(minutes=5), now=now() + dt.timedelta(minutes=5)
    )
    unmarked = await manager.unmark_episodes(user, show, [episode.id], now())

    assert marked.watched == {episode.id: tapped_at}
    assert again.watched == {episode.id: tapped_at}
    assert marked.status is TrackingStatus.WATCHING
    assert unmarked is not None
    assert unmarked.watched == {}
    assert unmarked.status is TrackingStatus.NOT_STARTED


async def test_statuses_follow_progress(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    manager = TrackingManager(db_session)
    airing = await cached_media(db_session, tmdb, "Still Airing")
    ended = await cached_media(db_session, tmdb, "Ended Already")

    added = await manager.set_show_status(user, airing, ShowTrackingChoice.WATCHING, now())
    caught_up = await manager.mark_episodes(
        user, airing, [e.id for e in aired_regular(await episodes_of(db_session, airing))], now(), now=now()
    )
    finished = await manager.mark_episodes(
        user, ended, [e.id for k, e in (await episodes_of(db_session, ended)).items() if k[0] != 0], now(), now=now()
    )

    assert added.status is TrackingStatus.NOT_STARTED
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

    tracking = await manager.mark_episodes(user, show, [*dated, undated], now(), now=now())

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
    await manager.mark_episodes(user, show, [episodes[1, 2].id], today, now=now())

    await manager.mark_episodes(user, show, [episodes[1, 1].id], today - dt.timedelta(days=400), now=now())

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
    await manager.mark_episodes(user, show, [episodes[1, 1].id, episodes[1, 2].id], now(), now=now())

    stopped = await manager.set_show_status(user, show, ShowTrackingChoice.STOPPED, now())
    still_stopped = await manager.unmark_episodes(user, show, [episodes[1, 2].id], now())
    back = await manager.mark_episodes(user, show, [episodes[1, 2].id], now(), now=now())

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
    never_started = await manager.set_show_status(user, show, ShowTrackingChoice.WATCH_LATER, now())
    await manager.mark_episodes(user, show, [episodes[1, 1].id], now(), now=now())

    aside = await manager.set_show_status(user, show, ShowTrackingChoice.WATCH_LATER, now())
    back = await manager.mark_episodes(user, show, [episodes[1, 2].id], now(), now=now())
    await manager.set_show_status(user, show, ShowTrackingChoice.WATCH_LATER, now())
    resumed = await manager.set_show_status(user, show, ShowTrackingChoice.WATCHING, now())

    # Put aside before it was started, it is not "not started": it waits apart.
    assert never_started.status is TrackingStatus.WATCH_LATER
    assert aside.status is TrackingStatus.WATCH_LATER
    assert back.status is TrackingStatus.WATCHING
    assert resumed.status is TrackingStatus.WATCHING


async def test_episodes_of_another_show_are_refused(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    show = await cached_media(db_session, tmdb, "Mine")
    other = await cached_media(db_session, tmdb, "Other")
    foreign = (await episodes_of(db_session, other))[1, 1]

    with pytest.raises(UnknownEpisodesError):
        await TrackingManager(db_session).mark_episodes(user, show, [foreign.id], now(), now=now())


async def test_movies_are_watched_or_to_watch_later(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    movie = await cached_media(db_session, tmdb, "Paper Moons", MediaType.MOVIE)
    manager, watched_at = TrackingManager(db_session), now()

    later = await manager.set_movie_watched(user, movie, watched=False, at=watched_at, now=watched_at)
    watched = await manager.set_movie_watched(user, movie, watched=True, at=watched_at, now=watched_at)

    assert (later.status, later.watched_at) == (TrackingStatus.WATCH_LATER, None)
    assert (watched.status, watched.watched_at) == (TrackingStatus.WATCHED, watched_at)
    with pytest.raises(FutureWatchError):
        await manager.set_movie_watched(user, movie, watched=True, at=now() + dt.timedelta(hours=1), now=now())


async def test_marking_a_watched_movie_again_keeps_its_first_watch(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    movie = await cached_media(db_session, tmdb, "Twice Seen", MediaType.MOVIE)
    manager, first = TrackingManager(db_session), now() - dt.timedelta(days=3)
    await manager.set_movie_watched(user, movie, watched=True, at=first, now=now())

    again = await manager.set_movie_watched(user, movie, watched=True, at=now(), now=now())

    assert (again.status, again.watched_at) == (TrackingStatus.WATCHED, first)


async def test_removing_a_show_forgets_what_was_watched(db_session: AsyncSession, tmdb: TMDBClient, user: User) -> None:
    show = await cached_media(db_session, tmdb, "Gone Soon")
    manager = TrackingManager(db_session)
    await manager.mark_episodes(user, show, [(await episodes_of(db_session, show))[1, 1].id], now(), now=now())

    await manager.untrack(user, show)

    assert await manager.show_tracking(user, show) is None
    assert (await manager.set_show_status(user, show, ShowTrackingChoice.WATCHING, now())).watched == {}


async def test_the_library_counts_aired_and_watched_regular_episodes(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Counted Show")
    episodes = await episodes_of(db_session, show)
    manager = TrackingManager(db_session)
    await manager.mark_episodes(user, show, [episodes[0, 1].id, episodes[1, 1].id, episodes[1, 2].id], now(), now=now())

    items = {item.media.id: item for item in await manager.library(user, MediaType.TV, now())}

    assert (items[show.id].watched_count, items[show.id].aired_count) == (2, 5)
    assert items[show.id].status is TrackingStatus.WATCHING


async def test_seasons_count_their_episodes_watched_and_aired_specials_last(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Seasons Show")
    episodes = await episodes_of(db_session, show)
    manager = TrackingManager(db_session)
    await manager.mark_episodes(user, show, [episodes[1, 1].id, episodes[2, 1].id], now(), now=now())

    seasons = await manager.seasons(user, show, now())

    # S02E03 airs in a week; the fake show's seasons are titled after their number.
    assert [(s.season_number, s.episode_count, s.watched_count, s.aired_count) for s in seasons] == [
        (1, 3, 1, 3),
        (2, 3, 1, 2),
        (0, 1, 0, 1),
    ]
    assert all(isinstance(season, SeasonSummary) for season in seasons)


async def test_record_watches_marks_many_shows_resuming_only_those_not_kept_aside(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    manager = TrackingManager(db_session)
    resumed = await cached_media(db_session, tmdb, "Resumed Show")
    aside = await cached_media(db_session, tmdb, "Aside Show")
    for show in (resumed, aside):
        await manager.set_show_status(user, show, ShowTrackingChoice.STOPPED, now())
    later, earlier = now() + dt.timedelta(days=1), now() - dt.timedelta(days=3)

    await manager.record_watches(
        user,
        {
            resumed: {(await episodes_of(db_session, resumed))[1, 1].id: later},
            aside: {(await episodes_of(db_session, aside))[1, 1].id: earlier},
        },
        now=now(),
        keep_aside={aside.id},
    )

    resumed_tracking = await manager.show_tracking(user, resumed)
    aside_tracking = await manager.show_tracking(user, aside)
    assert resumed_tracking is not None
    assert aside_tracking is not None
    assert resumed_tracking.status is TrackingStatus.WATCHING
    # A date after now is now's.
    assert next(iter(resumed_tracking.watched.values())) <= now()
    assert aside_tracking.status is TrackingStatus.STOPPED
    assert list(aside_tracking.watched.values()) == [earlier]


async def test_a_refresh_updates_the_status_of_everyone_tracking_the_show(
    db_session: AsyncSession, tmdb: TMDBClient, user: User
) -> None:
    show = await cached_media(db_session, tmdb, "Refreshed Show")
    manager = TrackingManager(db_session)
    await manager.mark_episodes(
        user, show, [e.id for e in aired_regular(await episodes_of(db_session, show))], now(), now=now()
    )

    # Eight days later, the last episode has aired.
    await manager.refresh_statuses(show, now() + dt.timedelta(days=8))

    tracking = await manager.show_tracking(user, show)
    assert tracking is not None
    assert tracking.status is TrackingStatus.WATCHING
    show = await CatalogManager(db_session, tmdb).fetch(MediaType.TV, show.tmdb_id, now())
    assert show.title == "Refreshed Show"


async def test_the_status_of_a_watch_dated_in_the_past_counts_what_aired_since(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    show, episodes = await add_show(
        db_session, {(1, 1): now() - dt.timedelta(days=10), (1, 2): now() - dt.timedelta(days=2)}
    )

    tracking = await TrackingManager(db_session).mark_episodes(
        user, show, [episodes[1, 1].id], now() - dt.timedelta(days=5), now=now()
    )

    assert tracking.status is TrackingStatus.WATCHING


async def test_a_watch_after_now_and_an_episode_airing_later_are_refused(db_session: AsyncSession) -> None:
    user = await add_user(db_session)
    show, episodes = await add_show(
        db_session, {(1, 1): now() - dt.timedelta(days=1), (1, 2): now() + dt.timedelta(days=1), (1, 3): None}
    )
    manager = TrackingManager(db_session)

    with pytest.raises(FutureWatchError):
        await manager.mark_episodes(user, show, [episodes[1, 1].id], now() + dt.timedelta(hours=1), now=now())
    with pytest.raises(UnairedEpisodesError):
        await manager.mark_episodes(user, show, [episodes[1, 1].id, episodes[1, 2].id], now(), now=now())
    # Without a date, an episode may have aired: it can be marked.
    marked = await manager.mark_episodes(user, show, [episodes[1, 3].id], now(), now=now())
    assert list(marked.watched) == [episodes[1, 3].id]
