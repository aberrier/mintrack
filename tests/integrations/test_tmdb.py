import asyncio
import datetime as dt
import typing

import pytest

from mintrack.db.models import MediaType
from mintrack.integrations.tmdb.client import TMDBClient, TMDBNotConfiguredError, TMDBNotFoundError
from mintrack.integrations.tmdb.schemas import TMDBMovie
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
