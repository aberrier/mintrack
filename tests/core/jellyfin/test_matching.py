import collections.abc
import dataclasses
import datetime as dt
import itertools

import pytest

from mintrack.core.jellyfin.matching import Found, JellyfinSeasons, SeasonGroup, WatchEvent, match, unmatched_item
from mintrack.db.models import JellyfinUnmatchedReason, MediaType
from mintrack.integrations.jellyfin.client import Item
from mintrack.integrations.tmdb.client import ExternalSource
from mintrack.integrations.tmdb.schemas import TMDBSearchResult

AT = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
MATRIX = 603
THRONES = 1399
# Two seasons of three episodes and one special.
THRONES_EPISODES = frozenset({(0, 1), (1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)})
ANIME = 37854
# Six episodes, all in season 1.
ANIME_EPISODES = frozenset((1, number) for number in range(1, 7))


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
        self.media = {(MediaType.MOVIE, MATRIX), (MediaType.TV, THRONES), (MediaType.TV, ANIME)}
        self.searches: list[str] = []
        # Episodes TMDB no longer lists, kept because someone watched or rated them.
        self.kept: frozenset[tuple[int, int]] = frozenset()
        self.groups: dict[int, list[SeasonGroup]] = {}

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
        return await self.listed_episode_numbers(show_id) | self.kept

    async def listed_episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        return {THRONES: THRONES_EPISODES, ANIME: ANIME_EPISODES}.get(show_id, frozenset())

    async def season_groups(self, show_id: int) -> collections.abc.Sequence[SeasonGroup]:
        return self.groups.get(show_id, [])


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


def episode(
    season: int | None,
    number: int | None,
    provider_ids: dict[str, str | None] | None = None,
    name: str = "Winter Is Coming",
) -> Item:
    return Item.model_validate(
        {
            "Id": "e",
            "Type": "Episode",
            "Name": name,
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


@dataclasses.dataclass
class FakeJellyfinSeasons:
    """Jellyfin's answers for any series: its number of regular seasons, and of episodes in each season."""

    count: int
    sizes: dict[int, int] = dataclasses.field(default_factory=dict)

    async def regular_count(self, series_id: str) -> int:
        return self.count

    async def season_sizes(self, series_id: str) -> dict[int, int]:
        return self.sizes


def jellyfin_seasons(count: int, sizes: dict[int, int] | None = None) -> JellyfinSeasons:
    return FakeJellyfinSeasons(count, sizes or {})


def split(*sizes: int) -> SeasonGroup:
    """An episode group splitting TMDB's season 1 into seasons of these sizes, numbered from 1."""
    numbers = itertools.count(1)
    return {order: tuple((1, next(numbers)) for _ in range(size)) for order, size in enumerate(sizes, start=1)}


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


@pytest.mark.parametrize(("season", "number"), [(1, 0), (None, None)])
async def test_an_episode_without_usable_numbers_is_matched_by_its_own_ids(
    catalog: FakeCatalog, season: int | None, number: int | None
) -> None:
    special = episode(season, number, {"Imdb": "tt1480055"})

    assert await match(special, AT, series({"Tmdb": "1399"}), catalog) == episode_watch(1, 1)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SHOW02E03 Ice and Fire", episode_watch(2, 3)),
        ("show s2e3", episode_watch(2, 3)),
        # After a show's initials, a code TMDB has no episode for.
        ("ANTM14E07", JellyfinUnmatchedReason.EPISODE_NOT_FOUND),
        # A release version.
        ("Show - S01E02v2", episode_watch(1, 2)),
        # Checksums, bracketed or not.
        ("[Group] Show - S01E02 (1080p) [A1E2B3C4]", episode_watch(1, 2)),
        ("Show - S01E02 AB12E345", episode_watch(1, 2)),
        ("Show AB12E345", JellyfinUnmatchedReason.NO_NUMBERS),
        # A code only in brackets, two codes, a multi-episode file, a year.
        ("[Group] Show (S01E02)", JellyfinUnmatchedReason.NO_NUMBERS),
        ("[Group] Show [S01E02]", JellyfinUnmatchedReason.NO_NUMBERS),
        ("Show S01E02 S01E03", JellyfinUnmatchedReason.NO_NUMBERS),
        ("Show S01E02E03", JellyfinUnmatchedReason.NO_NUMBERS),
        ("Show 2024E01", JellyfinUnmatchedReason.NO_NUMBERS),
    ],
)
async def test_an_episode_without_numbers_is_matched_by_the_one_episode_code_in_its_name(
    catalog: FakeCatalog, name: str, expected: WatchEvent | JellyfinUnmatchedReason
) -> None:
    assert await match(episode(None, None, name=name), AT, series({"Tmdb": "1399"}), catalog) == expected


async def test_the_episode_code_in_a_name_is_only_read_for_a_known_series(catalog: FakeCatalog) -> None:
    gone_series = episode(None, None, name="Show S02E03")

    assert await match(gone_series, AT, {}, catalog) is JellyfinUnmatchedReason.NO_NUMBERS


async def test_a_regular_episode_matches_its_jellyfin_numbering_before_its_own_ids(catalog: FakeCatalog) -> None:
    # Its IMDb id names TMDB's S01E01.
    regular = episode(1, 2, {"Imdb": "tt1480055"})

    assert await match(regular, AT, series({"Tmdb": "1399"}), catalog) == episode_watch(1, 2)


@pytest.mark.parametrize(
    "special",
    [
        # Its own ids win over the code in its name.
        episode(None, None, {"Imdb": "tt1480055"}, name="Show S02E03"),
        # And over TMDB's season 0 numbering, which Jellyfin's specials often do not follow.
        episode(0, 1, {"Imdb": "tt1480055"}),
    ],
)
async def test_an_episode_without_numbers_or_a_special_is_matched_by_its_own_ids_first(
    catalog: FakeCatalog, special: Item
) -> None:
    assert await match(special, AT, series({"Tmdb": "1399"}), catalog) == episode_watch(1, 1)


@pytest.mark.parametrize(
    ("groups", "sizes", "expected"),
    [
        # The one group splitting the show as Jellyfin does: S02E02 is TMDB's S01E05.
        ([split(3, 3)], {1: 3, 2: 3}, WatchEvent(MediaType.TV, ANIME, AT, 1, 5)),
        # Outvoting a group that numbers the same seasons differently, while splits into cours do not vote.
        (
            [split(3, 3), split(3, 3), {1: split(3)[1], 2: ((1, 6), (1, 2), (1, 3))}, split(2, 2, 2)],
            {1: 3, 2: 3},
            WatchEvent(MediaType.TV, ANIME, AT, 1, 5),
        ),
        # A single group whose season 2 is not Jellyfin's.
        ([split(2, 4)], {1: 3, 2: 3}, None),
        # A group whose season 2 has Jellyfin's size but season 1 does not.
        ([split(2, 3)], {1: 3, 2: 3}, None),
        # Many broadcast splits, none with Jellyfin's season 2.
        ([split(2, 2, 2), split(1, 5), split(4, 2), split(5, 1)], {1: 3, 2: 3}, None),
        # Two groups splitting as Jellyfin does disagree.
        ([split(3, 3), {1: split(3)[1], 2: ((1, 6), (1, 2), (1, 3))}], {1: 3, 2: 3}, None),
        # A group naming an episode TMDB does not have.
        ([{1: split(3)[1], 2: ((1, 7), (1, 8), (1, 9))}], {1: 3, 2: 3}, None),
        # Jellyfin has only the first two episodes of its season 2: still airing or downloading.
        ([split(3, 3)], {1: 3, 2: 2}, None),
        # Jellyfin cannot tell the size of its season 2.
        ([split(3, 3)], {1: 3}, None),
    ],
)
async def test_a_season_tmdb_merged_into_season_1_is_matched_through_the_groups_splitting_it_as_jellyfin_does(
    catalog: FakeCatalog, groups: list[SeasonGroup], sizes: dict[int, int], expected: WatchEvent | None
) -> None:
    catalog.groups[ANIME] = groups
    jellyfin_episode = episode(2, 2)

    found = await match(jellyfin_episode, AT, series({"Tmdb": str(ANIME)}), catalog, jellyfin_seasons(2, sizes))

    assert found == (JellyfinUnmatchedReason.EPISODE_NOT_FOUND if expected is None else expected)


async def test_an_episode_past_the_size_of_its_jellyfin_season_gets_no_group_vote(catalog: FakeCatalog) -> None:
    catalog.groups[ANIME] = [split(3, 3)]

    found = await match(episode(2, 4), AT, series({"Tmdb": str(ANIME)}), catalog, jellyfin_seasons(2, {1: 3, 2: 3}))

    assert found is JellyfinUnmatchedReason.EPISODE_NOT_FOUND


async def test_episode_groups_are_only_read_for_a_show_tmdb_lists_in_one_season(catalog: FakeCatalog) -> None:
    catalog.groups[THRONES] = [{1: ((1, 1),), 3: ((2, 1),)}]

    found = await match(episode(3, 1), AT, series({"Tmdb": "1399"}), catalog, jellyfin_seasons(3, {3: 1}))

    assert found is JellyfinUnmatchedReason.EPISODE_NOT_FOUND


@pytest.mark.parametrize(
    ("number", "expected"),
    [(4, episode_watch(2, 1)), (6, episode_watch(2, 3)), (7, JellyfinUnmatchedReason.EPISODE_NOT_FOUND)],
)
async def test_an_absolute_number_past_tmdb_season_1_matches_the_episode_at_that_place(
    catalog: FakeCatalog, number: int, expected: WatchEvent | JellyfinUnmatchedReason
) -> None:
    found = await match(episode(1, number), AT, series({"Tmdb": "1399"}), catalog, jellyfin_seasons(1))

    assert found == expected


@pytest.mark.parametrize("regular_seasons", [jellyfin_seasons(2), None])
async def test_an_absolute_number_is_guessed_only_when_jellyfin_has_one_regular_season(
    catalog: FakeCatalog, regular_seasons: JellyfinSeasons | None
) -> None:
    # Jellyfin's season 1 runs longer than TMDB's, but Jellyfin has a season 2 too (the seasons are split
    # differently), or its seasons are not known.
    found = await match(episode(1, 4), AT, series({"Tmdb": "1399"}), catalog, regular_seasons)

    assert found is JellyfinUnmatchedReason.EPISODE_NOT_FOUND


async def test_an_absolute_number_counts_only_the_episodes_tmdb_lists(catalog: FakeCatalog) -> None:
    # S01E04 is gone from TMDB, kept because someone watched it: the 5th episode is still S02E02.
    catalog.kept = frozenset({(1, 4)})

    found = await match(episode(1, 5), AT, series({"Tmdb": "1399"}), catalog, jellyfin_seasons(1))

    assert found == episode_watch(2, 2)


async def test_specials_match_their_season_0_number_and_never_an_absolute_one(catalog: FakeCatalog) -> None:
    one_season = jellyfin_seasons(1)

    assert await match(episode(0, 1), AT, series({"Tmdb": "1399"}), catalog, one_season) == episode_watch(0, 1)
    assert (
        await match(episode(0, 4), AT, series({"Tmdb": "1399"}), catalog, one_season)
        is JellyfinUnmatchedReason.EPISODE_NOT_FOUND
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
