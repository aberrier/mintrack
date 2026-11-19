import datetime as dt

import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.jellyfin import managers
from mintrack.core.jellyfin.managers import JellyfinManager
from mintrack.db.models import (
    Episode,
    JellyfinAccount,
    JellyfinSyncStatus,
    JellyfinUnmatchedReason,
    Media,
    MediaType,
    User,
    WatchedEpisode,
    WatchedMovie,
)
from mintrack.integrations.jellyfin import client
from mintrack.integrations.tmdb.client import TMDBClient
from tests.fakes.jellyfin import SERVER_URL, FakeJellyfin
from tests.fakes.tmdb import FakeTMDB, media_id

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
    # A TMDB id TMDB does not have.
    jellyfin.play_movie(bob, {"Tmdb": "99999999"}, DAY_3)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await watched(db_session, user) == set()
    assert (account.last_sync_status, account.last_sync_imported, account.last_sync_skipped) == (
        JellyfinSyncStatus.OK,
        0,
        3,
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


async def test_items_without_known_ids_match_by_title_and_year_or_by_their_episode_ids(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient, fake_tmdb: FakeTMDB
) -> None:
    fake_tmdb.release_years["Paper Moons"] = 2019
    fake_tmdb.external_episode_ids[("tvdb_id", "7001")] = (1399, 2, 1)
    jellyfin.play_movie(bob, {}, DAY_1, name="Paper Moons", year=2019)
    jellyfin.play_episode(bob, "deleted-series", 1, 9, DAY_2, {"Tvdb": "7001"})
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    paper_moons = media_id(MediaType.MOVIE, "Paper Moons")
    assert await watched(db_session, user) == {(paper_moons, None, None, DAY_1), (1399, 2, 1, DAY_2)}
    assert account.last_sync_unmatched == []


async def test_a_full_sync_describes_the_items_not_matched_once_per_series_not_found(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    # TMDB has a show of that title, but from another year.
    unknown = jellyfin.add_series({}, name="Nowhere Show", year=2020)
    jellyfin.play_episode(bob, unknown, 1, 1, DAY_1)
    jellyfin.play_episode(bob, unknown, 1, 2, DAY_1 + dt.timedelta(hours=1))
    known = jellyfin.add_series({"Tmdb": "1399"}, name="Paper Moons")
    jellyfin.play_episode(bob, known, 3, 1, DAY_2, {"Tvdb": "42"})
    jellyfin.play_movie(bob, {"Imdb": "tt404"}, DAY_3, name="Lost Film", year=1990)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert account.last_sync_skipped == 4
    assert [(item["name"], item["series_name"], item["reason"]) for item in account.last_sync_unmatched] == [
        ("Episode 1", "Nowhere Show", JellyfinUnmatchedReason.NOT_FOUND),
        ("Episode 1", "Paper Moons", JellyfinUnmatchedReason.EPISODE_NOT_FOUND),
        ("Lost Film", None, JellyfinUnmatchedReason.NOT_FOUND),
    ]
    assert account.last_sync_unmatched[1] == {
        "name": "Episode 1",
        "type": "Episode",
        "year": None,
        "provider_ids": {"Tvdb": "42"},
        "series_name": "Paper Moons",
        "series_year": None,
        "series_provider_ids": {"Tmdb": "1399"},
        "season": 3,
        "episode": 1,
        "reason": JellyfinUnmatchedReason.EPISODE_NOT_FOUND,
    }

    # Only a full sync knows every item not matched.
    jellyfin.play_movie(bob, {}, NOW)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)
    assert (account.last_sync_skipped, len(account.last_sync_unmatched)) == (4, 3)


async def test_the_sync_report_describes_only_the_first_items_not_matched(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(managers, "MAX_REPORTED_UNMATCHED", 1)
    jellyfin.play_movie(bob, {}, DAY_1, name="First")
    jellyfin.play_movie(bob, {}, DAY_2, name="Second")
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert account.last_sync_skipped == 2
    assert [item["name"] for item in account.last_sync_unmatched] == ["First"]


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

    async def find(*_: object) -> dict[str, list[dict[str, int]]]:
        raise RuntimeError

    jellyfin.play_movie(bob, {"Imdb": "tt1"}, DAY_1 + dt.timedelta(days=6))
    monkeypatch.setattr(TMDBClient, "find", find)

    with pytest.raises(RuntimeError):
        await JellyfinManager(db_session).sync(account, tmdb, NOW)

    await db_session.refresh(account)
    assert account.synced_until == DAY_1 + dt.timedelta(days=4)
    assert account.last_sync_status == JellyfinSyncStatus.FAILED


async def test_a_server_with_endless_history_fails_the_sync_instead_of_filling_the_memory(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(managers, "MAX_PLAYED_ITEMS", 1)
    jellyfin.play_movie(bob, {"Tmdb": "603"}, DAY_1)
    jellyfin.play_movie(bob, {"Tmdb": "604"}, DAY_2)
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert account.last_sync_status is JellyfinSyncStatus.FAILED
    assert await watched_ids(db_session, user) == set()


@pytest.mark.parametrize("fails", [False, True])
async def test_an_account_unlinked_during_its_sync_ends_it_quietly(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fails: bool,
) -> None:
    jellyfin.play_movie(bob, {"Tmdb": "603"}, DAY_1)
    account = await link(db_session, user)
    played_items = client.JellyfinClient.played_items

    async def unlinked_meanwhile(self: client.JellyfinClient, user_id: str, start_index: int) -> client.ItemsPage:
        await db_session.execute(sa.delete(JellyfinAccount).where(JellyfinAccount.id == account.id))
        await db_session.commit()
        if fails:
            raise RuntimeError
        return await played_items(self, user_id, start_index)

    monkeypatch.setattr(client.JellyfinClient, "played_items", unlinked_meanwhile)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await db_session.scalar(sa.select(JellyfinAccount).where(JellyfinAccount.id == account.id)) is None


async def test_a_play_dated_after_now_is_recorded_now(
    db_session: AsyncSession, user: User, jellyfin: FakeJellyfin, bob: str, tmdb: TMDBClient
) -> None:
    jellyfin.play_movie(bob, {"Tmdb": "603"}, NOW + dt.timedelta(hours=2))
    account = await link(db_session, user)

    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    assert await watched(db_session, user) == {(603, None, None, NOW)}


async def test_a_full_sync_never_moves_the_cursor_back(
    db_session: AsyncSession,
    user: User,
    jellyfin: FakeJellyfin,
    bob: str,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(managers, "BATCH_SIZE", 1)
    jellyfin.play_movie(bob, {"Tmdb": "603"}, DAY_1)
    jellyfin.play_movie(bob, {"Tmdb": "604"}, DAY_3)
    account = await link(db_session, user)
    await JellyfinManager(db_session).sync(account, tmdb, NOW)

    async def find(*_: object) -> dict[str, list[dict[str, int]]]:
        raise RuntimeError

    # The full pass commits its first batch, played on DAY_1, then fails on the next one.
    jellyfin.play_movie(bob, {"Imdb": "tt1"}, DAY_2)
    monkeypatch.setattr(TMDBClient, "find", find)
    with pytest.raises(RuntimeError):
        await JellyfinManager(db_session).sync(account, tmdb, NOW, full=True)

    await db_session.refresh(account)
    assert account.synced_until == DAY_3
