"""A fake TMDB speaking its protocol for the routes MinTrack uses.

A search for any query returns one show and one movie titled after the query, with ids derived from it, so each test
gets its own media; a search of one type returns the one of that type. Trending lists one show and one movie per
title of `trending`. A show has two seasons of three episodes and one special, dated relative to today: the last episode
airs in a week, unless the title starts with "Ended" (it aired) or "Undated" (no date yet). A title starting with
"Daily" has 10,000 episodes in its first season. Run it for browser tests with
`uv run uvicorn tests.fakes.tmdb:app --host 0.0.0.0 --port 8001`.
"""

import collections.abc
import dataclasses
import datetime as dt
import typing
import zlib

import fastapi
import fastapi.responses

from mintrack.db.models import MediaType

INVALID_KEY = "rejected-4f1c9e-key"
MAX_ID = 10_000_000
DAILY_EPISODES = 10_000
TRENDING = ("Trending One", "Trending Two")


def media_id(kind: str, query: str) -> int:
    return zlib.crc32(f"{kind}:{query}".encode()) % MAX_ID + 1


@dataclasses.dataclass
class FakeTMDB:
    titles: dict[int, str] = dataclasses.field(default_factory=dict)
    # (show id, season, episode) TMDB no longer lists.
    dropped: set[tuple[int, int, int]] = dataclasses.field(default_factory=set)
    # (external source, external id) -> ("movie" or "tv", TMDB id), for /find.
    external_ids: dict[tuple[str, str], tuple[str, int]] = dataclasses.field(default_factory=dict)
    trending: tuple[str, ...] = TRENDING

    def title(self, tmdb_id: int, kind: str) -> str:
        return self.titles.get(tmdb_id, f"{kind} {tmdb_id}")

    def episodes(self, tmdb_id: int, season: int) -> list[dict[str, typing.Any]]:
        today = dt.datetime.now(dt.UTC).date()
        title = self.title(tmdb_id, "Show")
        last = {"Ended": -1, "Undated": None}.get(title.split(" ")[0], 7)
        by_season: dict[int, list[int | None]] = {0: [-20], 1: [-30, -29, -28], 2: [-7, -1, last]}
        offsets = by_season[season]
        if season == 1 and title.startswith("Daily"):
            offsets = [-1] * DAILY_EPISODES
        return [
            {
                "season_number": season,
                "episode_number": number,
                "name": f"Episode {number}",
                "overview": f"What happens in episode {number}.",
                "still_path": None,
                "vote_average": 7.5,
                "vote_count": 12 * number,
                "air_date": "" if offset is None else (today + dt.timedelta(days=offset)).isoformat(),
            }
            for number, offset in enumerate(offsets, start=1)
            if (tmdb_id, season, number) not in self.dropped
        ]

    def season(self, tmdb_id: int, season: int) -> dict[str, typing.Any]:
        episodes = self.episodes(tmdb_id, season)
        return {
            "season_number": season,
            "name": "Specials" if season == 0 else f"Season {season}",
            "poster_path": None,
            "air_date": episodes[0]["air_date"] if episodes else "",
            "episodes": episodes,
        }

    def show(self, tmdb_id: int, appended: list[str]) -> dict[str, typing.Any]:
        title = self.title(tmdb_id, "Show")
        data: dict[str, typing.Any] = {
            "id": tmdb_id,
            "name": title,
            "overview": f"The story of {title}.",
            "poster_path": None,
            "backdrop_path": f"/backdrop-{tmdb_id}.jpg",
            "networks": [{"id": 1, "name": "Channel Nine"}],
            "first_air_date": self.episodes(tmdb_id, 1)[0]["air_date"],
            "status": "Ended" if title.startswith("Ended") else "Returning Series",
            "seasons": [{"season_number": number} for number in (0, 1, 2)],
            "vote_average": 8.25,
            "vote_count": 1234,
        }
        for item in appended:
            if item == "external_ids":
                data[item] = {"tvdb_id": tmdb_id}
            elif item.startswith("season/"):
                data[item] = self.season(tmdb_id, int(item.removeprefix("season/")))
        return data

    def movie(self, tmdb_id: int) -> dict[str, typing.Any]:
        return {
            "id": tmdb_id,
            "title": self.title(tmdb_id, "Movie"),
            "overview": "",
            "poster_path": None,
            "backdrop_path": f"/backdrop-{tmdb_id}.jpg",
            "runtime": 118,
            "release_date": "2020-05-01",
            "status": "Released",
            # TMDB's answer for a movie nobody voted for.
            "vote_average": 0,
            "vote_count": 0,
        }

    def result(self, kind: MediaType, title: str) -> dict[str, typing.Any]:
        """A search or trending result of that kind, whose title its pages then answer."""
        tmdb_id = media_id(kind, title)
        self.titles[tmdb_id] = title
        if kind is MediaType.TV:
            return {"id": tmdb_id, "name": title, "first_air_date": "2024-01-10"}
        return {"id": tmdb_id, "title": title, "release_date": ""}

    def add_search_routes(self, app: fastapi.FastAPI) -> None:
        @app.get("/3/search/multi")
        def search(query: str) -> dict[str, typing.Any]:
            results = [
                {"media_type": "tv"} | self.result(MediaType.TV, query),
                {"media_type": "movie"} | self.result(MediaType.MOVIE, query),
                {"id": 1, "media_type": "person", "name": query},
            ]
            return {"page": 1, "total_pages": 1, "results": results}

        @app.get("/3/search/{kind}")
        def search_type(kind: MediaType, query: str) -> dict[str, typing.Any]:
            return {"page": 1, "total_pages": 1, "results": [self.result(kind, query)]}

        @app.get("/3/trending/{kind}/week")
        def trending(kind: MediaType) -> dict[str, typing.Any]:
            results = [{"media_type": kind} | self.result(kind, title) for title in self.trending]
            return {"page": 1, "total_pages": 1, "results": results}

    def build_app(self) -> fastapi.FastAPI:
        app = fastapi.FastAPI()

        @app.middleware("http")
        async def check_key(
            request: fastapi.Request,
            call_next: collections.abc.Callable[[fastapi.Request], collections.abc.Awaitable[fastapi.Response]],
        ) -> fastapi.Response:
            if request.query_params.get("api_key") in {None, INVALID_KEY}:
                return fastapi.responses.JSONResponse({"status_message": "Invalid API key"}, status_code=401)
            return await call_next(request)

        self.add_search_routes(app)

        @app.get("/3/tv/{tmdb_id}")
        def show(tmdb_id: int, append_to_response: str = "") -> dict[str, typing.Any]:
            if tmdb_id > MAX_ID:
                raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND)
            return self.show(tmdb_id, append_to_response.split(","))

        @app.get("/3/movie/{tmdb_id}")
        def movie(tmdb_id: int) -> dict[str, typing.Any]:
            if tmdb_id > MAX_ID:
                raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND)
            return self.movie(tmdb_id)

        @app.get("/3/find/{external_id}")
        def find(external_id: str, external_source: str) -> dict[str, typing.Any]:
            results: dict[str, list[dict[str, typing.Any]]] = {"movie_results": [], "tv_results": []}
            if found := self.external_ids.get((external_source, external_id)):
                kind, tmdb_id = found
                results[f"{kind}_results"].append({"id": tmdb_id})
            return results

        return app


fake = FakeTMDB()
app = fake.build_app()
