import datetime as dt

import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.jellyfin import managers
from mintrack.core.jellyfin.managers import JellyfinManager
from mintrack.db.models import Episode, JellyfinAccount, JellyfinSyncStatus, Media, User, WatchedEpisode, WatchedMovie
from mintrack.integrations.tmdb.client import TMDBClient
from tests.fakes.jellyfin import SERVER_URL, FakeJellyfin
from tests.fakes.tmdb import FakeTMDB

NOW = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
DAY_1 = dt.datetime(2026, 11, 1, 20, tzinfo=dt.UTC)
DAY_2 = DAY_1 + dt.timedelta(days=1)
DAY_3 = DAY_1 + dt.timedelta(days=2)


@pytest.fixture
def bob(jellyfin: FakeJellyfin) -> str:
    jellyfin.add_user("bob", "secret")
    return "bob"


async def link(db_session: AsyncSession, user: User) -> JellyfinAccount:
    return await JellyfinManager(db_session).link(user, SERVER_URL, "bob", "secret")


async def watched(session: AsyncSession, user: User) -> set[tuple[int, int | None, int | None, dt.datetime]]:
    """What the user watched: (show or movie TMDB id, season, episode, when)."""
    movies = await session.execute(
        sa.select(Media.tmdb_id, WatchedMovie.watched_at)
        .join(WatchedMovie, WatchedMovie.media_id == Media.id)
        .where(WatchedMovie.user_id == user.id)
    )
    episodes = await session.execute(
        sa.select(Media.tmdb_id, Episode.season_number, Episode.episode_number, WatchedEpisode.watched_at)
        .join(Episode, Episode.media_id == Media.id)
        .join(WatchedEpisode, WatchedEpisode.episode_id == Episode.id)
        .where(WatchedEpisode.user_id == user.id)
    )
    return {(tmdb_id, None, None, at) for tmdb_id, at in movies} | {tuple(row) for row in episodes}


async def watched_ids(session: AsyncSession, user: User) -> set[int]:
    return {tmdb_id for tmdb_id, *_ in await watched(session, user)}


async def test_first_sync_imports_the_played_history_oldest_first(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    show = jellyfin.add_series({"Tmdb": "1399"})
    jellyfin.play_episode(bob, show, 1, 2, DAY_2)
    jellyfin.play_movie(bob, {"Tmdb": "603", "Imdb": "tt0133093"}, DAY_1)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await watched(db_session, user) == {(603, None, None, DAY_1), (1399, 1, 2, DAY_2)}
    assert (account.synced_until, account.last_sync_at, account.last_sync_status) == (DAY_2, NOW, JellyfinSyncStatus.OK)
    assert (account.last_sync_imported, account.last_sync_skipped) == (2, 0)


async def test_next_syncs_read_only_what_was_played_since_the_cursor(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    jellyfin.play_movie(bob, {"Tmdb": "603"}, DAY_1)
    jellyfin.play_movie(bob, {"Tmdb": "604"}, DAY_2)
    account = await link(db_session, user)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    jellyfin.play_movie(bob, {"Tmdb": "605"}, DAY_3)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    # The movie played at the cursor is read again; tracking ignores a watch it already has.
    assert await watched_ids(db_session, user) == {603, 604, 605}
    assert (account.synced_until, account.last_sync_imported) == (DAY_3, 1)


async def test_unmatched_items_are_counted_and_undated_ones_left_out(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    jellyfin.play_movie(bob, {}, DAY_1)
    jellyfin.play_movie(bob, {"Tmdb": "603"}, None)
    jellyfin.play_episode(bob, "deleted-series", 1, 1, DAY_2)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await watched(db_session, user) == set()
    assert (account.last_sync_status, account.last_sync_imported, account.last_sync_skipped) == (
        JellyfinSyncStatus.OK,
        0,
        2,
    )


async def test_external_ids_are_looked_up_and_episodes_tmdb_does_not_list_are_skipped(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient, fake_tmdb: FakeTMDB
) -> None:
    fake_tmdb.external_ids[("imdb_id", "tt0133093")] = ("movie", 603)
    fake_tmdb.external_ids[("tvdb_id", "121361")] = ("tv", 1399)
    show = jellyfin.add_series({"Tvdb": "121361"})
    jellyfin.play_movie(bob, {"Imdb": "tt0133093"}, DAY_1)
    jellyfin.play_episode(bob, show, 1, 1, DAY_2)
    jellyfin.play_episode(bob, show, 9, 1, DAY_3)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await watched(db_session, user) == {(603, None, None, DAY_1), (1399, 1, 1, DAY_2)}
    assert (account.last_sync_imported, account.last_sync_skipped) == (2, 1)


async def test_a_full_sync_picks_up_items_skipped_before(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    jellyfin.play_movie(bob, {}, DAY_1)
    jellyfin.play_movie(bob, {"Tmdb": "604"}, DAY_2)
    account = await link(db_session, user)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)
    # The user identifies the movie in Jellyfin.
    jellyfin.played[bob][0]["ProviderIds"] = {"Tmdb": "603"}

    await JellyfinManager(db_session).sync(account, tmdb, NOW)
    assert await watched_ids(db_session, user) == {604}
    # Only re-read the latest item: the count still says what the full read found.
    assert account.last_sync_skipped == 1

    await JellyfinManager(db_session).sync(account, tmdb, NOW, full=True)
    assert await watched_ids(db_session, user) == {603, 604}
    assert (account.synced_until, account.last_sync_skipped) == (DAY_2, 0)


async def test_a_revoked_token_is_recorded_and_keeps_the_last_success(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    jellyfin.play_movie(bob, {"Tmdb": "603"}, DAY_1)
    account = await link(db_session, user)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)
    jellyfin.revoke_tokens()

    await JellyfinManager(db_session).sync(account, tmdb, NOW + dt.timedelta(minutes=15))

    assert account.last_sync_status == JellyfinSyncStatus.UNAUTHORIZED
    assert (account.last_sync_at, account.last_success_at) == (NOW + dt.timedelta(minutes=15), NOW)
    assert (account.last_sync_imported, account.synced_until) == (1, DAY_1)


async def test_an_unreachable_server_is_recorded(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    respx_mock: respx.Router,
    tmdb: TMDBClient,
) -> None:
    account = await link(db_session, user)
    respx_mock.get(f"{SERVER_URL}/Items").respond(503)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert account.last_sync_status == JellyfinSyncStatus.UNREACHABLE


async def test_a_failing_batch_keeps_the_batches_before_it(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(managers, "BATCH_SIZE", 2)
    for day in range(1, 6):
        jellyfin.play_movie(bob, {"Tmdb": str(day)}, DAY_1 + dt.timedelta(days=day))
    account = await link(db_session, user)

    async def find(*_: object) -> int | None:
        raise RuntimeError

    jellyfin.play_movie(bob, {"Imdb": "tt1"}, DAY_1 + dt.timedelta(days=6))
    monkeypatch.setattr(managers, "tmdb_finder", lambda _tmdb: find)

    with pytest.raises(RuntimeError):
        await JellyfinManager(db_session).sync(account, tmdb, NOW)

    await db_session.refresh(account)
    assert account.synced_until == DAY_1 + dt.timedelta(days=4)
    assert account.last_sync_status == JellyfinSyncStatus.FAILED
