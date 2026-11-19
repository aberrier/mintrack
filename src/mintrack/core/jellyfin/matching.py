import collections.abc
import dataclasses
import datetime as dt
import typing
import unicodedata

from mintrack.db.models import JellyfinUnmatchedItem, JellyfinUnmatchedReason, MediaType
from mintrack.integrations.jellyfin.client import Item
from mintrack.integrations.tmdb.client import ExternalSource
from mintrack.integrations.tmdb.schemas import TMDBSearchResult


@dataclasses.dataclass(frozen=True)
class WatchEvent:
    media_type: MediaType
    tmdb_id: int
    watched_at: dt.datetime
    season_number: int | None = None
    episode_number: int | None = None


@dataclasses.dataclass(frozen=True)
class Found:
    """What TMDB's /find knows under one external id."""

    movies: tuple[int, ...] = ()
    shows: tuple[int, ...] = ()
    # (show TMDB id, season, episode)
    episodes: tuple[tuple[int, int, int], ...] = ()


class Catalog(typing.Protocol):
    """The TMDB lookups matching needs."""

    async def find(self, source: ExternalSource, external_id: str) -> Found: ...

    async def search(self, media_type: MediaType, title: str) -> collections.abc.Sequence[TMDBSearchResult]: ...

    async def exists(self, media_type: MediaType, tmdb_id: int) -> bool: ...

    async def episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        """(season, episode) of every episode stored for a show `exists` found, those TMDB no longer lists but
        someone watched or rated included."""
        ...

    async def listed_episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        """(season, episode) of the episodes TMDB lists now for a show `exists` found."""
        ...


# Jellyfin provider keys tried in order after Tmdb: the TMDB id is then looked up from the external id.
EXTERNAL_PROVIDERS = (("Imdb", ExternalSource.IMDB), ("Tvdb", ExternalSource.TVDB))
# Years a title search accepts between Jellyfin's production year and TMDB's release, after the exact year.
YEAR_TOLERANCE = 1
# The number of regular seasons (specials aside) Jellyfin has for a series, by its Jellyfin id.
type RegularSeasons = collections.abc.Callable[[str], collections.abc.Awaitable[int]]


async def match(
    item: Item,
    played_at: dt.datetime,
    series: collections.abc.Mapping[str, Item],
    catalog: Catalog,
    regular_seasons: RegularSeasons | None = None,
) -> WatchEvent | JellyfinUnmatchedReason:
    """The watch a played movie or episode stands for, or why none was found. Without `regular_seasons`, an episode
    is never matched by its absolute number."""
    if item.type == "Movie":
        tmdb_id = await _media_id(item, MediaType.MOVIE, catalog)
        return JellyfinUnmatchedReason.NOT_FOUND if tmdb_id is None else WatchEvent(MediaType.MOVIE, tmdb_id, played_at)
    if item.type != "Episode":
        return JellyfinUnmatchedReason.UNSUPPORTED
    season, number = item.parent_index_number, item.index_number
    if season is None or number is None or season < 0 or number < 1:
        return JellyfinUnmatchedReason.NO_NUMBERS
    found = await _episode(item, series.get(item.series_id or ""), (season, number), catalog, regular_seasons)
    if isinstance(found, JellyfinUnmatchedReason):
        return found
    show_id, season, number = found
    return WatchEvent(MediaType.TV, show_id, played_at, season, number)


def unmatched_item(
    item: Item, series: collections.abc.Mapping[str, Item], reason: JellyfinUnmatchedReason
) -> JellyfinUnmatchedItem:
    """What Jellyfin says of an item no watch was found for, for the sync report."""
    show = series.get(item.series_id or "")
    return {
        "name": item.name,
        "type": item.type,
        "year": item.production_year,
        "provider_ids": _provider_ids(item),
        "series_name": item.series_name,
        "series_year": None if show is None else show.production_year,
        "series_provider_ids": None if show is None else _provider_ids(show),
        "season": item.parent_index_number,
        "episode": item.index_number,
        "reason": reason,
    }


def _provider_ids(item: Item) -> dict[str, str]:
    return {provider: id_ for provider, id_ in sorted(item.provider_ids.items()) if id_}


async def _tmdb_ids(item: Item, media_type: MediaType, catalog: Catalog) -> collections.abc.AsyncIterator[int]:
    """The TMDB ids the item's provider ids point to: its Tmdb id, then what TMDB finds for its IMDb and TVDB ids."""
    if (tmdb := item.provider_ids.get("Tmdb")) and tmdb.isdecimal():
        yield int(tmdb)
    for provider, source in EXTERNAL_PROVIDERS:
        if external_id := item.provider_ids.get(provider):
            found = await catalog.find(source, external_id)
            for tmdb_id in found.movies if media_type is MediaType.MOVIE else found.shows:
                yield tmdb_id


async def _media_id(item: Item, media_type: MediaType, catalog: Catalog) -> int | None:
    """The movie or show TMDB has under the item's provider ids, else the one its title and year name."""
    async for tmdb_id in _tmdb_ids(item, media_type, catalog):
        if await catalog.exists(media_type, tmdb_id):
            return tmdb_id
    tmdb_id = await _search(item, media_type, catalog)
    return tmdb_id if tmdb_id is not None and await catalog.exists(media_type, tmdb_id) else None


async def _episode(
    item: Item,
    show: Item | None,
    numbering: tuple[int, int],
    catalog: Catalog,
    regular_seasons: RegularSeasons | None,
) -> tuple[int, int, int] | JellyfinUnmatchedReason:
    """The TMDB show, season and number of an episode: Jellyfin's numbering in the series TMDB knows, else what TMDB
    finds under the episode's own ids, else its absolute number in that series when Jellyfin keeps the whole series
    in one regular season."""
    season, number = numbering
    show_id = None if show is None else await _media_id(show, MediaType.TV, catalog)
    numbers = frozenset() if show_id is None else await catalog.episode_numbers(show_id)
    if show_id is not None and (season, number) in numbers:
        return show_id, season, number
    for provider, source in EXTERNAL_PROVIDERS:
        if external_id := item.provider_ids.get(provider):
            for found_show, found_season, found_number in (await catalog.find(source, external_id)).episodes:
                if await catalog.exists(MediaType.TV, found_show) and (found_season, found_number) in (
                    await catalog.episode_numbers(found_show)
                ):
                    return found_show, found_season, found_number
    if show_id is None:
        return JellyfinUnmatchedReason.NOT_FOUND
    if season == 1 and item.series_id and regular_seasons is not None:
        absolute = _absolute(await catalog.listed_episode_numbers(show_id), number)
        # The cache may not have an episode TMDB added since it was refreshed. A season 2 in Jellyfin means its
        # season 1 is not the whole series: TVDB and TMDB just split the seasons differently.
        if absolute is not None and absolute in numbers and await regular_seasons(item.series_id) == 1:
            return show_id, *absolute
    return JellyfinUnmatchedReason.EPISODE_NOT_FOUND


def _absolute(listed: collections.abc.Set[tuple[int, int]], number: int) -> tuple[int, int] | None:
    """The episode at this absolute number among those TMDB lists, for a series Jellyfin keeps in one season and TMDB
    splits (anime, mostly): only past the last episode TMDB lists in season 1."""
    first_season = [episode for season_number, episode in listed if season_number == 1]
    if not first_season or number <= max(first_season):
        return None
    regular = sorted(episode for episode in listed if episode[0] >= 1)
    return regular[number - 1] if number <= len(regular) else None


def _normalized(title: str) -> str:
    """The title without case, accents and punctuation."""
    decomposed = unicodedata.normalize("NFKD", title.casefold())
    kept = "".join(char if char.isalnum() else " " for char in decomposed if not unicodedata.combining(char))
    return " ".join(kept.split())


async def _search(item: Item, media_type: MediaType, catalog: Catalog) -> int | None:
    """The one TMDB result with the item's title, released its production year or within a year: a title is only
    trusted when nothing else could be meant."""
    titles = {_normalized(title) for title in (item.name, item.original_title or "")} - {""}
    if not titles or item.production_year is None:
        return None
    released = [
        (result.id, result.release_date.year)
        for result in await catalog.search(media_type, item.name or item.original_title or "")
        if result.release_date is not None
        and titles & {_normalized(result.title), _normalized(result.original_title or "")}
    ]
    for tolerance in range(YEAR_TOLERANCE + 1):
        ids = {tmdb_id for tmdb_id, year in released if abs(year - item.production_year) <= tolerance}
        if ids:
            return ids.pop() if len(ids) == 1 else None
    return None
