import dataclasses

import httpx

from mintrack.integrations.tvmaze import TvmazeClient

TVMAZE_URL = "https://api.tvmaze.com"


@dataclasses.dataclass
class FakeTvmaze:
    """TVmaze's lookup and episode list over an httpx MockTransport.

    `shows` maps a TVDB id to the TVmaze id and its episodes as TVmaze sends them; `failing` lists TVmaze ids that
    answer 500.
    """

    shows: dict[int, tuple[int, list[dict[str, object]]]] = dataclasses.field(default_factory=dict)
    failing: set[int] = dataclasses.field(default_factory=set)
    requests: list[str] = dataclasses.field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(f"{request.url.path}?{request.url.query.decode()}".removesuffix("?"))
        if request.url.path == "/lookup/shows":
            show = self.shows.get(int(request.url.params["thetvdb"]))
            if show is None:
                return httpx.Response(404)
            return httpx.Response(301, headers={"Location": f"{TVMAZE_URL}/shows/{show[0]}"})
        tvmaze_id = int(request.url.path.split("/")[2])
        if tvmaze_id in self.failing:
            return httpx.Response(500)
        if request.url.path.endswith("/episodes"):
            episodes = next(episodes for show_id, episodes in self.shows.values() if show_id == tvmaze_id)
            return httpx.Response(200, json=episodes)
        return httpx.Response(200, json={"id": tvmaze_id})

    def client(self) -> TvmazeClient:
        transport = httpx.MockTransport(self.handle)
        return TvmazeClient(httpx.AsyncClient(transport=transport, base_url=TVMAZE_URL, follow_redirects=True))


def tvmaze_episode(season: int, number: int, airstamp: str | None, airtime: str = "21:00") -> dict[str, object]:
    return {"season": season, "number": number, "airtime": airtime if airstamp else "", "airstamp": airstamp}
