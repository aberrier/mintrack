import asyncio
import datetime as dt
import typing

import httpx
import pytest

from mintrack.db.models import MediaType
from mintrack.integrations.tmdb.client import TMDBClient, TMDBNotConfiguredError, TMDBNotFoundError
from mintrack.integrations.tmdb.config import TMDBConfig
from mintrack.integrations.tmdb.schemas import TMDBEpisodeGroup, TMDBMovie
from tests.conftest import make_tmdb_client
from tests.fakes.tmdb import INVALID_KEY, MAX_ID, FakeTMDB


def test_release_dates_without_a_date_are_skipped() -> None:
    releases = [
        {"type": 4, "release_date": None},
        {"type": 4, "release_date": ""},
        {"type": 4},
        {"type": 4, "release_date": "2026-03-02T00:00:00.000Z"},
    ]

    movie = TMDBMovie.model_validate(
        {"id": 1, "title": "Patchy", "release_dates": {"results": [{"release_dates": releases}]}}
    )

    assert movie.digital_release_date() == dt.date(2026, 3, 2)


async def test_search_returns_shows_and_movies_but_not_people(tmdb: TMDBClient) -> None:
    results = await tmdb.search("Orbit Kitchen")

    assert [(result.media_type, result.title) for result in results] == [
        (MediaType.TV, "Orbit Kitchen"),
        (MediaType.MOVIE, "Orbit Kitchen"),
    ]
    assert results[1].release_date is None


async def test_a_typed_search_returns_only_that_type(tmdb: TMDBClient) -> None:
    results = await tmdb.search("Orbit Kitchen", MediaType.MOVIE)

    assert [(result.media_type, result.title) for result in results] == [(MediaType.MOVIE, "Orbit Kitchen")]


async def test_trending_is_kept_for_an_hour_per_type(tmdb: TMDBClient, fake_tmdb: FakeTMDB) -> None:
    now = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
    fake_tmdb.trending = ("First Week",)
    first = await tmdb.trending(MediaType.TV, now)
    fake_tmdb.trending = ("Second Week",)

    cached = await tmdb.trending(MediaType.TV, now + dt.timedelta(minutes=59))
    other_type = await tmdb.trending(MediaType.MOVIE, now)
    refreshed = await tmdb.trending(MediaType.TV, now + dt.timedelta(hours=1))

    assert [result.title for result in first] == [result.title for result in cached] == ["First Week"]
    assert [(result.media_type, result.title) for result in other_type] == [(MediaType.MOVIE, "Second Week")]
    assert [result.title for result in refreshed] == ["Second Week"]


async def test_a_show_comes_with_every_season_and_its_episodes(tmdb: TMDBClient) -> None:
    show_id = (await tmdb.search("Paper Moons"))[0].id

    show = await tmdb.show(show_id)

    assert show.name == "Paper Moons"
    assert show.external_ids.tvdb_id == show_id
    assert (show.backdrop_path, [network.name for network in show.networks]) == (
        f"/backdrop-{show_id}.jpg",
        ["Channel Nine"],
    )
    assert [(season.season_number, len(season.episodes)) for season in show.seasons] == [(0, 1), (1, 3), (2, 3)]


async def test_errors_name_the_problem_but_never_the_key(fake_tmdb: FakeTMDB) -> None:
    with pytest.raises(TMDBNotFoundError):
        await make_tmdb_client(fake_tmdb).movie(MAX_ID + 1)
    with pytest.raises(TMDBNotConfiguredError, match="MINTRACK__TMDB__API_KEY"):
        await make_tmdb_client(fake_tmdb, api_key=None).search("anything")
    with pytest.raises(TMDBNotConfiguredError, match="TMDB rejected the key") as error:
        await make_tmdb_client(fake_tmdb, api_key=INVALID_KEY).search("anything")

    assert INVALID_KEY not in str(error.value)


async def test_requests_arriving_together_refill_the_trending_cache_once(
    tmdb: TMDBClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    get = tmdb._get  # noqa: SLF001

    async def counted(path: str, **params: str | int) -> dict[str, typing.Any]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return await get(path, **params)

    monkeypatch.setattr(tmdb, "_get", counted)
    now = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)

    await asyncio.gather(*(tmdb.trending(MediaType.TV, now) for _ in range(5)))

    assert calls == 1


def tmdb_answering(answers: dict[str, typing.Any]) -> TMDBClient:
    """A client of a TMDB answering these JSON bodies by path, and 404 to the others."""

    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/3/")
        return httpx.Response(200, json=answers[path]) if path in answers else httpx.Response(404)

    return TMDBClient(TMDBConfig(api_key="test-key"), transport=httpx.MockTransport(answer))


GROUP = {"groups": [{"order": 1, "episodes": [{"season_number": 1, "episode_number": 1, "order": 0}]}]}


@pytest.mark.parametrize(
    "answers",
    [
        # The show is gone.
        {},
        {"tv/1/episode_groups": [{"id": "g1", "type": 6}]},
        {"tv/1/episode_groups": {"results": "g1"}},
    ],
)
async def test_a_show_whose_episode_groups_tmdb_does_not_list_as_expected_has_none(
    answers: dict[str, typing.Any],
) -> None:
    assert await tmdb_answering(answers | {"tv/episode_group/g1": GROUP}).season_groups(1) == []


async def test_only_the_season_groups_tmdb_lists_and_answers_as_expected_are_read() -> None:
    results = [
        {"id": "kept", "type": 6},
        {"id": "kept", "type": 7},
        {"id": "arcs", "type": 5},
        {"id": 7, "type": 6},
        {"type": 7},
        {"id": "gone", "type": 7},
        {"id": "malformed", "type": 7},
        "group",
    ]
    answers = {
        "tv/1/episode_groups": {"results": results},
        "tv/episode_group/kept": GROUP,
        "tv/episode_group/arcs": GROUP,
        "tv/episode_group/malformed": {"groups": [{"order": 1, "episodes": [{"season_number": "one"}]}]},
    }

    groups = await tmdb_answering(answers).season_groups(1)

    assert [group.seasons() for group in groups] == [{1: ((1, 1),)}]


@pytest.mark.parametrize(
    ("orders", "expected"),
    [
        ([(0, 0), (1, 1), (2, 1)], {0: ((0, 1),), 1: ((1, 1),), 2: ((1, 1),)}),
        # Regular episodes in order 0: every season would be off by one.
        ([(0, 1), (1, 1)], None),
        ([(2, 1), (3, 1)], None),
        ([(1, 1), (1, 1)], None),
        ([(-1, 1), (1, 1)], None),
    ],
)
def test_an_episode_group_gives_seasons_only_when_its_orders_number_seasons_from_1(
    orders: list[tuple[int, int]], expected: dict[int, tuple[tuple[int, int], ...]] | None
) -> None:
    group = TMDBEpisodeGroup.model_validate(
        {
            "groups": [
                {"order": order, "episodes": [{"season_number": season, "episode_number": 1, "order": 0}]}
                for order, season in orders
            ]
        }
    )

    assert group.seasons() == expected


def test_an_episode_group_season_lists_its_episodes_by_their_order_in_the_group() -> None:
    episodes = [
        {"season_number": 1, "episode_number": number, "order": order} for number, order in ((6, 2), (7, 0), (5, 1))
    ]
    group = TMDBEpisodeGroup.model_validate({"groups": [{"order": 1, "episodes": episodes}]})

    assert group.seasons() == {1: ((1, 7), (1, 5), (1, 6))}
