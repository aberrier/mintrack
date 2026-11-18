import collections.abc
import dataclasses
import datetime as dt

from mintrack.db.models import MediaType
from mintrack.integrations.jellyfin.client import Item
from mintrack.integrations.tmdb.client import ExternalSource


@dataclasses.dataclass(frozen=True)
class WatchEvent:
    media_type: MediaType
    tmdb_id: int
    watched_at: dt.datetime
    season_number: int | None = None
    episode_number: int | None = None


type FindTmdbId = collections.abc.Callable[[ExternalSource, str, MediaType], collections.abc.Awaitable[int | None]]

# Jellyfin provider keys tried in order after Tmdb: the TMDB id is then looked up from the external id.
EXTERNAL_PROVIDERS = (("Imdb", ExternalSource.IMDB), ("Tvdb", ExternalSource.TVDB))


async def tmdb_id_of(item: Item, media_type: MediaType, find: FindTmdbId) -> int | None:
    """The item's TMDB id: its own Tmdb provider id, else the first IMDb or TVDB id TMDB knows."""
    if (tmdb := item.provider_ids.get("Tmdb")) and tmdb.isdecimal():
        return int(tmdb)
    for provider, source in EXTERNAL_PROVIDERS:
        if (external_id := item.provider_ids.get(provider)) and (found := await find(source, external_id, media_type)):
            return found
    return None


async def match(item: Item, series: collections.abc.Mapping[str, Item], find: FindTmdbId) -> WatchEvent | None:
    """The watch a played movie or episode stands for; episodes match on their series and Jellyfin's numbering."""
    watched_at = item.user_data.last_played_date
    if watched_at is None:
        return None
    if item.type == "Movie":
        tmdb_id = await tmdb_id_of(item, MediaType.MOVIE, find)
        return None if tmdb_id is None else WatchEvent(MediaType.MOVIE, tmdb_id, watched_at)
    season_number, episode_number = item.parent_index_number, item.index_number
    show = series.get(item.series_id or "")
    if item.type != "Episode" or show is None or season_number is None or episode_number is None:
        return None
    if season_number < 0 or episode_number < 1:
        return None
    tmdb_id = await tmdb_id_of(show, MediaType.TV, find)
    if tmdb_id is None:
        return None
    return WatchEvent(MediaType.TV, tmdb_id, watched_at, season_number, episode_number)
