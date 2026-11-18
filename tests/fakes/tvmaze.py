"""A fake TVmaze speaking its protocol for the routes MinTrack uses.

`shows` maps a TVDB id to the TVmaze id and its episodes as TVmaze sends them; `failing` lists TVmaze ids that answer
500. The app run for browser tests knows no show, so every show keeps its TMDB dates:
`uv run uvicorn tests.fakes.tvmaze:app --host 0.0.0.0 --port 8002`.
"""

import dataclasses
import typing

import fastapi
import fastapi.responses
import httpx

from mintrack.integrations.tvmaze.client import TvmazeClient

TVMAZE_URL = "https://api.tvmaze.com"


@dataclasses.dataclass
class FakeTvmaze:
    shows: dict[int, tuple[int, list[dict[str, object]]]] = dataclasses.field(default_factory=dict)
    failing: set[int] = dataclasses.field(default_factory=set)
    # Each request's path and query string.
    requests: list[str] = dataclasses.field(default_factory=list)
    hosts: set[str] = dataclasses.field(default_factory=set)
    user_agents: set[str] = dataclasses.field(default_factory=set)

    def build_app(self) -> fastapi.FastAPI:
        app = fastapi.FastAPI()

        @app.middleware("http")
        async def record(
            request: fastapi.Request,
            call_next: typing.Callable[[fastapi.Request], typing.Awaitable[fastapi.Response]],
        ) -> fastapi.Response:
            self.requests.append(f"{request.url.path}?{request.url.query}".removesuffix("?"))
            self.hosts.add(request.url.netloc)
            self.user_agents.add(request.headers.get("user-agent", ""))
            return await call_next(request)

        @app.get("/lookup/shows")
        def lookup(thetvdb: int, request: fastapi.Request) -> fastapi.Response:
            show = self.shows.get(thetvdb)
            if show is None:
                return fastapi.Response(status_code=404)
            return fastapi.responses.RedirectResponse(f"{request.base_url}shows/{show[0]}", status_code=301)

        @app.get("/shows/{tvmaze_id}")
        def show(tvmaze_id: int) -> fastapi.Response:
            if tvmaze_id in self.failing:
                return fastapi.Response(status_code=500)
            return fastapi.responses.JSONResponse({"id": tvmaze_id})

        @app.get("/shows/{tvmaze_id}/episodes")
        def episodes(tvmaze_id: int) -> fastapi.Response:
            if tvmaze_id in self.failing:
                return fastapi.Response(status_code=500)
            found = next((episodes for show_id, episodes in self.shows.values() if show_id == tvmaze_id), None)
            if found is None:
                return fastapi.Response(status_code=404)
            return fastapi.responses.JSONResponse(found)

        return app

    def transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.build_app())

    def client(self) -> TvmazeClient:
        return TvmazeClient(httpx.AsyncClient(transport=self.transport(), base_url=TVMAZE_URL, follow_redirects=True))


def tvmaze_episode(season: int, number: int, airstamp: str | None, airtime: str = "21:00") -> dict[str, object]:
    return {"season": season, "number": number, "airtime": airtime if airstamp else "", "airstamp": airstamp}


app = FakeTvmaze().build_app()
