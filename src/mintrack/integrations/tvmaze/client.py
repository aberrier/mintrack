import asyncio
import collections.abc
import contextlib
import datetime as dt

import httpx
import pydantic

from mintrack.config import get_config

BASE_URL = "https://api.tvmaze.com"
TIMEOUT_SECONDS = 10
# TVmaze allows about 20 calls every 10 seconds per IP address and answers 429 beyond.
RATE_LIMIT_WAIT_SECONDS = 10
ATTEMPTS = 3


class TvmazeEpisode(pydantic.BaseModel):
    season: int
    # None for the specials TVmaze lists among regular episodes.
    number: int | None
    # Empty when the network gives no time; the airstamp then only carries a date.
    airtime: str
    airstamp: dt.datetime | None

    @property
    def exact_airstamp(self) -> dt.datetime | None:
        return self.airstamp if self.airtime else None


_episodes = pydantic.TypeAdapter(list[TvmazeEpisode])


class TvmazeClient:
    """TVmaze's public API, which needs no key."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def lookup_show(self, tvdb_id: int) -> int | None:
        response = await self._get("/lookup/shows", params={"thetvdb": tvdb_id})
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return int(response.json()["id"])

    async def episodes(self, tvmaze_id: int) -> list[TvmazeEpisode]:
        # Without specials, which TVmaze numbers apart from TMDB's season 0.
        response = await self._get(f"/shows/{tvmaze_id}/episodes")
        response.raise_for_status()
        return _episodes.validate_json(response.content)

    async def _get(self, path: str, params: dict[str, int] | None = None) -> httpx.Response:
        for _ in range(ATTEMPTS - 1):
            response = await self._http.get(path, params=params)
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                return response
            await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS)
        return await self._http.get(path, params=params)


@contextlib.asynccontextmanager
async def tvmaze_client() -> collections.abc.AsyncGenerator[TvmazeClient]:
    headers = {"User-Agent": f"MinTrack/{get_config().project.version}"}
    # The lookup endpoint answers with a redirect to the show.
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=TIMEOUT_SECONDS, follow_redirects=True, headers=headers
    ) as http:
        yield TvmazeClient(http)
