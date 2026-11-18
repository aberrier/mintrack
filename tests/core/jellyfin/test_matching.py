import datetime as dt

import pytest

from mintrack.core.jellyfin.matching import WatchEvent, match
from mintrack.db.models import MediaType
from mintrack.integrations.jellyfin.client import Item
from mintrack.integrations.tmdb.client import ExternalSource

AT = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
KNOWN = {
    (ExternalSource.IMDB, "tt0133093", MediaType.MOVIE): 603,
    (ExternalSource.TVDB, "121361", MediaType.TV): 1399,
}


async def find(source: ExternalSource, external_id: str, media_type: MediaType) -> int | None:
    return KNOWN.get((source, external_id, media_type))


def movie(provider_ids: dict[str, str | None], at: dt.datetime | None = AT) -> Item:
    return Item.model_validate(
        {"Id": "m", "Type": "Movie", "ProviderIds": provider_ids, "UserData": {"LastPlayedDate": at}}
    )


def episode(season: int | None, number: int | None, series_id: str = "s") -> Item:
    return Item.model_validate(
        {
            "Id": "e",
            "Type": "Episode",
            "SeriesId": series_id,
            "ParentIndexNumber": season,
            "IndexNumber": number,
            "ProviderIds": {"Tmdb": "999999", "Tvdb": "1"},
            "UserData": {"LastPlayedDate": AT},
        }
    )


def series(provider_ids: dict[str, str | None]) -> dict[str, Item]:
    return {"s": Item.model_validate({"Id": "s", "Type": "Series", "ProviderIds": provider_ids})}


@pytest.mark.parametrize(
    ("provider_ids", "tmdb_id"),
    [
        ({"Tmdb": "603", "Imdb": "tt0000001"}, 603),
        ({"Tmdb": "", "Imdb": "tt0133093"}, 603),
        ({"Imdb": "tt0000001", "Tvdb": "x"}, None),
        ({"Tmdb": None}, None),
    ],
)
async def test_a_movie_matches_its_tmdb_id_then_imdb_then_tvdb(
    provider_ids: dict[str, str | None], tmdb_id: int | None
) -> None:
    expected = None if tmdb_id is None else WatchEvent(MediaType.MOVIE, tmdb_id, AT)
    assert await match(movie(provider_ids), {}, find) == expected


@pytest.mark.parametrize(
    "series_ids",
    [{"Tmdb": "1399"}, {"Imdb": "tt-unknown", "Tvdb": "121361"}],
)
async def test_an_episode_matches_its_series_and_jellyfin_numbering(series_ids: dict[str, str | None]) -> None:
    assert await match(episode(2, 3), series(series_ids), find) == WatchEvent(MediaType.TV, 1399, AT, 2, 3)


@pytest.mark.parametrize(("season", "number"), [(None, 1), (1, None), (-1, 1), (1, 0)])
async def test_an_episode_without_usable_numbers_is_not_matched(season: int | None, number: int | None) -> None:
    assert await match(episode(season, number), series({"Tmdb": "1399"}), find) is None


async def test_an_episode_whose_series_is_unknown_is_not_matched() -> None:
    assert await match(episode(1, 1, series_id="other"), series({"Tmdb": "1399"}), find) is None


async def test_an_item_never_played_with_a_date_is_not_matched() -> None:
    assert await match(movie({"Tmdb": "603"}, at=None), {}, find) is None
