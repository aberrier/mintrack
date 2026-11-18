import collections.abc
import datetime as dt
import enum
import functools
import itertools
import typing
import urllib.parse

import httpx

from mintrack.config import get_config
from mintrack.db.models import MediaType
from mintrack.observability.logging import logger

from .config import TMDBConfig
from .schemas import TMDBMovie, TMDBSearchResult, TMDBSeason, TMDBShow

TIMEOUT_SECONDS = 10
CONNECT_RETRIES = 3
# TMDB's limit of append_to_response items per request.
MAX_APPENDS = 20
TRENDING_MAX_AGE = dt.timedelta(hours=1)
SEARCHED_TYPES = frozenset(MediaType)


class ExternalSource(enum.StrEnum):
    IMDB = "imdb_id"
    TVDB = "tvdb_id"


class TMDBError(Exception):
    """TMDB cannot be reached or answered with an error."""


class TMDBNotConfiguredError(TMDBError):
    def __init__(self, message: str = "TMDB is not configured: set MINTRACK__TMDB__API_KEY") -> None:
        super().__init__(message)


class TMDBNotFoundError(TMDBError):
    pass


class TMDBClient:
    def __init__(self, config: TMDBConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.configured = config.api_key is not None
        params = {"language": config.language}
        if config.api_key is not None:
            params["api_key"] = config.api_key.get_secret_value()
        self.http = httpx.AsyncClient(
            base_url=str(config.url).removesuffix("/") + "/",
            params=params,
            timeout=TIMEOUT_SECONDS,
            transport=transport or httpx.AsyncHTTPTransport(retries=CONNECT_RETRIES),
        )
        # One client per configuration, so per language: media type -> (fetched at, results).
        self._trending: dict[MediaType, tuple[dt.datetime, list[TMDBSearchResult]]] = {}

    async def _get(self, path: str, **params: str | int) -> dict[str, typing.Any]:
        if not self.configured:
            raise TMDBNotConfiguredError
        try:
            response = await self.http.get(path, params=params)
        except httpx.HTTPError as error:
            # The exception names the URL, whose query holds the key: only its type is kept.
            msg = f"TMDB request failed: {type(error).__name__}"
            raise TMDBError(msg) from None
        if response.status_code == httpx.codes.NOT_FOUND:
            raise TMDBNotFoundError(path)
        if response.status_code == httpx.codes.UNAUTHORIZED:
            logger.warning("TMDB rejected the API key", path=path)
            msg = "TMDB rejected the key: check MINTRACK__TMDB__API_KEY"
            raise TMDBNotConfiguredError(msg)
        if response.is_error:
            msg = f"TMDB answered {response.status_code} to {path}"
            raise TMDBError(msg)
        return response.json()

    async def search(self, query: str, media_type: MediaType | None = None) -> list[TMDBSearchResult]:
        """TMDB's first page of results of that type, or of shows and movies."""
        if media_type is None:
            data = await self._get("search/multi", query=query, include_adult="false")
            return _results(data, SEARCHED_TYPES)
        data = await self._get(f"search/{media_type}", query=query, include_adult="false")
        return _results(data, {media_type}, media_type)

    async def trending(self, media_type: MediaType, now: dt.datetime) -> list[TMDBSearchResult]:
        """TMDB's first page of the week's trending shows or movies, kept for an hour."""
        if (cached := self._trending.get(media_type)) and now - cached[0] < TRENDING_MAX_AGE:
            return cached[1]
        results = _results(await self._get(f"trending/{media_type}/week"), {media_type}, media_type)
        self._trending[media_type] = (now, results)
        return results

    async def movie(self, tmdb_id: int) -> TMDBMovie:
        return TMDBMovie.model_validate(await self._get(f"movie/{tmdb_id}"))

    async def show(self, tmdb_id: int) -> TMDBShow:
        """The show with every season and its episodes."""
        data = await self._get(f"tv/{tmdb_id}", append_to_response="external_ids")
        numbers = [season["season_number"] for season in data.get("seasons") or []]
        seasons = []
        for batch in itertools.batched(numbers, MAX_APPENDS, strict=False):
            appended = await self._get(
                f"tv/{tmdb_id}", append_to_response=",".join(f"season/{number}" for number in batch)
            )
            seasons += [
                TMDBSeason.model_validate(appended[f"season/{number}"])
                for number in batch
                if f"season/{number}" in appended
            ]
        return TMDBShow.model_validate({**data, "seasons": seasons})

    async def find(self, external_id: str, source: ExternalSource) -> dict[str, typing.Any]:
        """TMDB ids of what has this external id: `movie_results`, `tv_results` and `tv_episode_results`."""
        return await self._get(f"find/{urllib.parse.quote(external_id, safe='')}", external_source=source)


def _results(
    data: dict[str, typing.Any], types: collections.abc.Set[MediaType], media_type: MediaType | None = None
) -> list[TMDBSearchResult]:
    """The results of those types; `media_type` is set where TMDB leaves it out, as in typed searches."""
    results = [result if media_type is None else {"media_type": media_type, **result} for result in data["results"]]
    return [TMDBSearchResult.model_validate(result) for result in results if result.get("media_type") in types]


@functools.cache
def get_tmdb_client() -> TMDBClient:
    return TMDBClient(get_config().tmdb)
