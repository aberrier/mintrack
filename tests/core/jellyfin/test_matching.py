import collections.abc
import datetime as dt

import pytest

from mintrack.core.jellyfin.matching import Found, WatchEvent, match, unmatched_item
from mintrack.db.models import JellyfinUnmatchedReason, MediaType
from mintrack.integrations.jellyfin.client import Item
from mintrack.integrations.tmdb.client import ExternalSource
from mintrack.integrations.tmdb.schemas import TMDBSearchResult

AT = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
MATRIX = 603
THRONES = 1399
# Two seasons of three episodes and one special.
THRONES_EPISODES = frozenset({(0, 1), (1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)})


class FakeCatalog:
    """TMDB as matching sees it: a movie, a show, what /find knows and what searches answer."""

    def __init__(self) -> None:
        self.found = {
            (ExternalSource.IMDB, "tt0133093"): Found(movies=(MATRIX,)),
            (ExternalSource.TVDB, "121361"): Found(shows=(THRONES,)),
            # An episode of the show, under its TVDB and IMDb ids.
            (ExternalSource.TVDB, "3254641"): Found(episodes=((THRONES, 2, 1),)),
            (ExternalSource.IMDB, "tt1480055"): Found(episodes=((THRONES, 1, 1),)),
        }
        self.results: dict[tuple[MediaType, str], list[TMDBSearchResult]] = {}
        self.media = {(MediaType.MOVIE, MATRIX), (MediaType.TV, THRONES)}
        self.searches: list[str] = []
        # Episodes TMDB no longer lists, kept because someone watched or rated them.
        self.kept: frozenset[tuple[int, int]] = frozenset()

    def answer(
        self, media_type: MediaType, query: str, *results: tuple[int, str, str], original_title: str | None = None
    ) -> None:
        self.results[media_type, query] = [
            TMDBSearchResult.model_validate(
                {
                    "id": tmdb_id,
                    "media_type": media_type,
                    "title": title,
                    "original_title": original_title,
                    "release_date": date,
                }
            )
            for tmdb_id, title, date in results
        ]
        self.media |= {(media_type, tmdb_id) for tmdb_id, *_ in results}

    async def find(self, source: ExternalSource, external_id: str) -> Found:
        return self.found.get((source, external_id), Found())

    async def search(self, media_type: MediaType, title: str) -> collections.abc.Sequence[TMDBSearchResult]:
        self.searches.append(title)
        return self.results.get((media_type, title), [])

    async def exists(self, media_type: MediaType, tmdb_id: int) -> bool:
        return (media_type, tmdb_id) in self.media

    async def episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        return THRONES_EPISODES | self.kept if show_id == THRONES else frozenset()

    async def listed_episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        return THRONES_EPISODES if show_id == THRONES else frozenset()


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


def movie(
    provider_ids: dict[str, str | None],
    name: str = "The Matrix",
    year: int | None = 1999,
    original_title: str | None = None,
) -> Item:
    return Item.model_validate(
        {
            "Id": "m",
            "Type": "Movie",
            "Name": name,
            "OriginalTitle": original_title,
            "ProductionYear": year,
            "ProviderIds": provider_ids,
        }
    )


def episode(season: int | None, number: int | None, provider_ids: dict[str, str | None] | None = None) -> Item:
    return Item.model_validate(
        {
            "Id": "e",
            "Type": "Episode",
            "Name": "Winter Is Coming",
            "ProductionYear": 2011,
            "SeriesId": "s",
            "SeriesName": "Game of Thrones",
            "ParentIndexNumber": season,
            "IndexNumber": number,
            "ProviderIds": provider_ids or {},
        }
    )


def series(provider_ids: dict[str, str | None], name: str = "Game of Thrones") -> dict[str, Item]:
    item = {"Id": "s", "Type": "Series", "Name": name, "ProductionYear": 2011, "ProviderIds": provider_ids}
    return {"s": Item.model_validate(item)}


def movie_watch(tmdb_id: int = MATRIX) -> WatchEvent:
    return WatchEvent(MediaType.MOVIE, tmdb_id, AT)


def episode_watch(season: int, number: int) -> WatchEvent:
    return WatchEvent(MediaType.TV, THRONES, AT, season, number)


@pytest.mark.parametrize(
    "provider_ids",
    [
        {"Tmdb": "603", "Imdb": "tt0000001"},
        {"Tmdb": "", "Imdb": "tt0133093"},
        # A Tmdb id TMDB no longer has, then the IMDb id.
        {"Tmdb": "999999", "Imdb": "tt0133093"},
    ],
)
async def test_a_movie_matches_its_tmdb_id_then_imdb_then_tvdb(
    catalog: FakeCatalog, provider_ids: dict[str, str | None]
) -> None:
    assert await match(movie(provider_ids), AT, {}, catalog) == movie_watch()


@pytest.mark.parametrize(
    ("name", "results"),
    [
        ("The Matrix", [(MATRIX, "The Matrix", "1999-03-31"), (2, "The Matrix Reloaded", "2003-05-15")]),
        # Case, accents and punctuation aside, a year off.
        ("Amelie!", [(MATRIX, "Amélie", "2000-04-25")]),
        # The exact year wins over the one a year off.
        ("Dune", [(MATRIX, "Dune", "1999-01-01"), (2, "Dune", "2000-01-01")]),
    ],
)
async def test_a_movie_without_known_ids_matches_the_one_search_result_of_its_title_and_year(
    catalog: FakeCatalog, name: str, results: list[tuple[int, str, str]]
) -> None:
    catalog.answer(MediaType.MOVIE, name, *results)

    assert await match(movie({"Imdb": "tt-unknown"}, name), AT, {}, catalog) == movie_watch()


@pytest.mark.parametrize(
    ("year", "results"),
    [
        # Two movies of that title and year.
        (1999, [(1, "The Matrix", "1999-03-31"), (2, "The Matrix", "1999-11-01")]),
        # Only other years.
        (1999, [(1, "The Matrix", "2003-03-31")]),
        # Only other titles.
        (1999, [(1, "The Matrix Reloaded", "1999-03-31")]),
        # No year to check.
        (None, [(1, "The Matrix", "1999-03-31")]),
        # No release date to check.
        (1999, [(1, "The Matrix", "")]),
    ],
)
async def test_a_movie_title_search_is_only_trusted_when_nothing_else_could_be_meant(
    catalog: FakeCatalog, year: int | None, results: list[tuple[int, str, str]]
) -> None:
    catalog.answer(MediaType.MOVIE, "The Matrix", *results)

    assert await match(movie({}, year=year), AT, {}, catalog) is JellyfinUnmatchedReason.NOT_FOUND


@pytest.mark.parametrize("series_ids", [{"Tmdb": "1399"}, {"Imdb": "tt-unknown", "Tvdb": "121361"}])
async def test_an_episode_matches_its_series_and_jellyfin_numbering(
    catalog: FakeCatalog, series_ids: dict[str, str | None]
) -> None:
    assert await match(episode(2, 3), AT, series(series_ids), catalog) == episode_watch(2, 3)


async def test_a_series_without_known_ids_matches_the_one_show_of_its_title_and_year(catalog: FakeCatalog) -> None:
    catalog.answer(MediaType.TV, "Game of Thrones", (THRONES, "Game of Thrones", "2011-04-17"))

    assert await match(episode(1, 2), AT, series({}), catalog) == episode_watch(1, 2)


@pytest.mark.parametrize(
    ("series_items", "provider_ids", "expected"),
    [
        # The series is gone from Jellyfin: the episode's TVDB id names the show and TMDB's numbering.
        ({}, {"Tvdb": "3254641"}, episode_watch(2, 1)),
        # Jellyfin numbers the episode differently from TMDB.
        (series({"Tmdb": "1399"}), {"Tvdb": "unknown", "Imdb": "tt1480055"}, episode_watch(1, 1)),
    ],
)
async def test_an_episode_falls_back_on_its_own_ids(
    catalog: FakeCatalog, series_items: dict[str, Item], provider_ids: dict[str, str | None], expected: WatchEvent
) -> None:
    jellyfin_numbering = episode(5, 9, provider_ids)

    assert await match(jellyfin_numbering, AT, series_items, catalog) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [(4, episode_watch(2, 1)), (6, episode_watch(2, 3)), (7, JellyfinUnmatchedReason.EPISODE_NOT_FOUND)],
)
async def test_an_absolute_number_past_tmdb_season_1_matches_the_episode_at_that_place(
    catalog: FakeCatalog, number: int, expected: WatchEvent | JellyfinUnmatchedReason
) -> None:
    assert await match(episode(1, number), AT, series({"Tmdb": "1399"}), catalog) == expected


async def test_an_absolute_number_is_not_guessed_when_jellyfin_has_a_season_2(catalog: FakeCatalog) -> None:
    # Jellyfin's season 1 runs longer than TMDB's, but Jellyfin has a season 2 too: the seasons are split differently.
    played_seasons = {"s": {1, 2}}

    found = await match(episode(1, 4), AT, series({"Tmdb": "1399"}), catalog, played_seasons)

    assert found is JellyfinUnmatchedReason.EPISODE_NOT_FOUND


async def test_an_absolute_number_counts_only_the_episodes_tmdb_lists(catalog: FakeCatalog) -> None:
    # S01E04 is gone from TMDB, kept because someone watched it: the 5th episode is still S02E02.
    catalog.kept = frozenset({(1, 4)})

    found = await match(episode(1, 5), AT, series({"Tmdb": "1399"}), catalog, {"s": {1}})

    assert found == episode_watch(2, 2)


async def test_specials_match_their_season_0_number_and_never_an_absolute_one(catalog: FakeCatalog) -> None:
    assert await match(episode(0, 1), AT, series({"Tmdb": "1399"}), catalog) == episode_watch(0, 1)
    assert (
        await match(episode(0, 4), AT, series({"Tmdb": "1399"}), catalog) is JellyfinUnmatchedReason.EPISODE_NOT_FOUND
    )


@pytest.mark.parametrize(
    ("original_title", "expected"),
    [("Le Fabuleux Destin", movie_watch()), (None, JellyfinUnmatchedReason.NOT_FOUND)],
)
async def test_a_movie_named_in_another_language_matches_by_its_original_title(
    catalog: FakeCatalog, original_title: str | None, expected: WatchEvent | JellyfinUnmatchedReason
) -> None:
    # Jellyfin names it in the library's language; TMDB's result has another title and the same original one.
    name = "Die fabelhafte Welt"
    catalog.answer(MediaType.MOVIE, name, (MATRIX, "Amelie", "2001-04-25"), original_title="Le Fabuleux Destin")

    assert await match(movie({}, name, 2001, original_title), AT, {}, catalog) == expected


@pytest.mark.parametrize(
    ("released", "expected"), [("2000-06-01", movie_watch()), ("2001-06-01", JellyfinUnmatchedReason.NOT_FOUND)]
)
async def test_a_title_search_accepts_a_year_off_but_not_two(
    catalog: FakeCatalog, released: str, expected: WatchEvent | JellyfinUnmatchedReason
) -> None:
    catalog.answer(MediaType.MOVIE, "The Matrix", (MATRIX, "The Matrix", released))

    assert await match(movie({}, year=1999), AT, {}, catalog) == expected


@pytest.mark.parametrize(
    ("item", "series_items", "reason"),
    [
        (episode(None, 1), series({"Tmdb": "1399"}), JellyfinUnmatchedReason.NO_NUMBERS),
        (episode(1, None), series({"Tmdb": "1399"}), JellyfinUnmatchedReason.NO_NUMBERS),
        (episode(-1, 1), series({"Tmdb": "1399"}), JellyfinUnmatchedReason.NO_NUMBERS),
        (episode(1, 0), series({"Tmdb": "1399"}), JellyfinUnmatchedReason.NO_NUMBERS),
        (episode(3, 1), series({"Tmdb": "1399"}), JellyfinUnmatchedReason.EPISODE_NOT_FOUND),
        (episode(1, 1), series({"Tvdb": "0"}), JellyfinUnmatchedReason.NOT_FOUND),
        (episode(1, 1), {}, JellyfinUnmatchedReason.NOT_FOUND),
        (Item.model_validate({"Id": "t", "Type": "Trailer"}), {}, JellyfinUnmatchedReason.UNSUPPORTED),
    ],
)
async def test_items_not_matched_say_why(
    catalog: FakeCatalog, item: Item, series_items: dict[str, Item], reason: JellyfinUnmatchedReason
) -> None:
    assert await match(item, AT, series_items, catalog) is reason


async def test_an_unmatched_episode_is_described_with_its_series() -> None:
    item = episode(1, 1, {"Tvdb": "3254641", "Imdb": None})

    described = unmatched_item(item, series({"Tvdb": "121361"}), JellyfinUnmatchedReason.NOT_FOUND)

    assert described == {
        "name": "Winter Is Coming",
        "type": "Episode",
        "year": 2011,
        "provider_ids": {"Tvdb": "3254641"},
        "series_name": "Game of Thrones",
        "series_year": 2011,
        "series_provider_ids": {"Tvdb": "121361"},
        "season": 1,
        "episode": 1,
        "reason": JellyfinUnmatchedReason.NOT_FOUND,
    }
