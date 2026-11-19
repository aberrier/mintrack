import collections
import collections.abc
import dataclasses
import datetime as dt
import re
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


# One way of splitting a show into seasons: season number -> TMDB (season, episode) of its episodes, in order.
type SeasonGroup = collections.abc.Mapping[int, collections.abc.Sequence[tuple[int, int]]]


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

    async def season_groups(self, show_id: int) -> collections.abc.Sequence[SeasonGroup]:
        """TMDB's episode groups splitting a show `exists` found into seasons."""
        ...


class JellyfinSeasons(typing.Protocol):
    """What Jellyfin has of a series, by its Jellyfin id; None when Jellyfin cannot tell."""

    async def regular_count(self, series_id: str) -> int | None:
        """The number of its regular seasons, specials aside."""
        ...

    async def season_sizes(self, series_id: str) -> collections.abc.Mapping[int, int] | None:
        """The number of episodes with a file in each of its seasons, for a season holding exactly episodes 1 to that
        number."""
        ...


# Jellyfin provider keys tried in order after Tmdb: the TMDB id is then looked up from the external id.
EXTERNAL_PROVIDERS = (("Imdb", ExternalSource.IMDB), ("Tvdb", ExternalSource.TVDB))
# An episode code in a name Jellyfin gave no numbers to: S03E04, s3e4, or after a show's initials (ANTM14E07), with
# an optional release version (S03E04v2). Neither a digit nor an E comes just before it, so S01E02E03 has none.
EPISODE_CODE = re.compile(r"(?<![0-9E])S?(\d{1,2})E(\d{1,3})(?:V\d)?(?![0-9A-Z])", re.IGNORECASE)
# Parts of a file name where a code is never meant: bracketed ones (release group, checksum, video format) and an
# unbracketed CRC32 checksum, eight hexadecimal digits (AB12E345).
NOT_CODES = re.compile(r"\[[^\]]*\]|\([^)]*\)|\b[0-9A-F]{8}\b", re.IGNORECASE)
# Years a title search accepts between Jellyfin's production year and TMDB's release, after the exact year.
YEAR_TOLERANCE = 1


async def match(
    item: Item,
    played_at: dt.datetime,
    series: collections.abc.Mapping[str, Item],
    catalog: Catalog,
    seasons: JellyfinSeasons | None = None,
) -> WatchEvent | JellyfinUnmatchedReason:
    """The watch a played movie or episode stands for, or why none was found. Without `seasons`, an episode is never
    matched by its absolute number or TMDB's episode groups.

    An episode without usable numbers (none, or an episode 0 Jellyfin files a special under) is matched by its own
    ids, else by an episode code in its name when its series is known. A special is matched by its own ids first."""
    if item.type == "Movie":
        tmdb_id = await _media_id(item, MediaType.MOVIE, catalog)
        return JellyfinUnmatchedReason.NOT_FOUND if tmdb_id is None else WatchEvent(MediaType.MOVIE, tmdb_id, played_at)
    if item.type != "Episode":
        return JellyfinUnmatchedReason.UNSUPPORTED
    show = series.get(item.series_id or "")
    numbering = _numbering(item.parent_index_number, item.index_number)
    found = await _own_episode(item, catalog) if _own_ids_first(item) else None
    if found is None:
        if numbering is None and show is not None:
            numbering = _name_code(item.name)
        if numbering is None:
            return JellyfinUnmatchedReason.NO_NUMBERS
        found = await _episode(item, show, numbering, catalog, seasons)
    if isinstance(found, JellyfinUnmatchedReason):
        return found
    show_id, season, number = found
    return WatchEvent(MediaType.TV, show_id, played_at, season, number)


def _numbering(season: int | None, number: int | None) -> tuple[int, int] | None:
    return None if season is None or number is None or season < 0 or number < 1 else (season, number)


def _own_ids_first(item: Item) -> bool:
    """Whether an episode is matched by its own ids before its numbers: it has no usable numbers, or is a special."""
    numbering = _numbering(item.parent_index_number, item.index_number)
    return numbering is None or numbering[0] == 0


def _name_code(name: str) -> tuple[int, int] | None:
    """The season and number of the one episode code in a name, outside its bracketed parts."""
    codes = EPISODE_CODE.findall(NOT_CODES.sub(" ", name))
    return None if len(codes) != 1 else _numbering(int(codes[0][0]), int(codes[0][1]))


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
    seasons: JellyfinSeasons | None,
) -> tuple[int, int, int] | JellyfinUnmatchedReason:
    """The TMDB show, season and number of an episode: Jellyfin's numbering in the series TMDB knows, else what TMDB
    finds under the episode's own ids (unless `match` tried them first), else its place in TMDB's seasons when the
    two split the show differently."""
    season, number = numbering
    show_id = None if show is None else await _media_id(show, MediaType.TV, catalog)
    numbers = frozenset() if show_id is None else await catalog.episode_numbers(show_id)
    if show_id is not None and (season, number) in numbers:
        return show_id, season, number
    if not _own_ids_first(item) and (own := await _own_episode(item, catalog)) is not None:
        return own
    if show_id is None:
        return JellyfinUnmatchedReason.NOT_FOUND
    if item.series_id and seasons is not None:
        found = await _split_differently(item.series_id, show_id, numbering, catalog, seasons)
        # The cache may not have an episode TMDB added since it was refreshed.
        if found is not None and found in numbers:
            return show_id, *found
    return JellyfinUnmatchedReason.EPISODE_NOT_FOUND


async def _split_differently(
    series_id: str, show_id: int, numbering: tuple[int, int], catalog: Catalog, seasons: JellyfinSeasons
) -> tuple[int, int] | None:
    """TMDB's season and number of an episode when TMDB and Jellyfin split the show differently: its place in the
    seasons TMDB's episode groups split a show it lists in one season into, else its absolute number when Jellyfin
    keeps the whole series in one regular season."""
    season, number = numbering
    numbers = await catalog.episode_numbers(show_id)
    if season > 1 and _one_regular_season(numbers):
        sizes = await seasons.season_sizes(series_id)
        if sizes is not None and number <= sizes.get(season, 0):
            return _grouped(await catalog.season_groups(show_id), season, number, sizes)
    if season == 1:
        absolute = _absolute(await catalog.listed_episode_numbers(show_id), number)
        # A season 2 in Jellyfin means its season 1 is not the whole series: TVDB and TMDB just split the seasons
        # differently. Jellyfin is only asked for an episode the cache has.
        if absolute is not None and absolute in numbers and await seasons.regular_count(series_id) == 1:
            return absolute
    return None


def _one_regular_season(numbers: collections.abc.Set[tuple[int, int]]) -> bool:
    """Whether TMDB has every regular episode of a show in its season 1, as for many anime."""
    return {season for season, _ in numbers if season >= 1} == {1}


async def _own_episode(item: Item, catalog: Catalog) -> tuple[int, int, int] | None:
    """The TMDB show, season and number TMDB finds under the episode's own IMDb or TVDB id."""
    for provider, source in EXTERNAL_PROVIDERS:
        if external_id := item.provider_ids.get(provider):
            for show_id, season, number in (await catalog.find(source, external_id)).episodes:
                if await catalog.exists(MediaType.TV, show_id) and (season, number) in (
                    await catalog.episode_numbers(show_id)
                ):
                    return show_id, season, number
    return None


def _grouped(
    groups: collections.abc.Sequence[SeasonGroup], season: int, number: int, sizes: collections.abc.Mapping[int, int]
) -> tuple[int, int] | None:
    """The TMDB numbers that more than half of the groups splitting the show as Jellyfin does give episode `number`
    (within Jellyfin's season size) of a season. Only a group whose seasons 1 to `season` have Jellyfin's `sizes`
    votes: one splitting the show into cours or broadcast seasons is left out, a season Jellyfin has only part of
    (downloading, still airing) matches no group's size, and no majority means no match."""
    voting = [
        group[season]
        for group in groups
        if all(len(group.get(earlier, ())) == sizes.get(earlier) for earlier in range(1, season + 1))
    ]
    if not voting:
        return None
    [(episode, count)] = collections.Counter(episodes[number - 1] for episodes in voting).most_common(1)
    return episode if count * 2 > len(voting) else None


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
