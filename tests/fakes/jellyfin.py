import collections.abc
import datetime as dt
import itertools
import json
import secrets

import httpx
import pytest
import respx

from mintrack.config import get_config

SERVER_URL = "http://127.0.0.1:8096"
SERVER_ID = "f4ke5erver"
SECRET_KEY = "pytest-secret-key-of-at-least-32-characters"


class FakeJellyfin:
    """A Jellyfin server answering the calls MinTrack makes, from in-memory users and played items."""

    def __init__(self, router: respx.Router, url: str = SERVER_URL) -> None:
        self.passwords: dict[str, str] = {}
        self.tokens: dict[str, str] = {}
        self.devices: dict[str, str] = {}
        self.played: dict[str, list[dict]] = {}
        self.series: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []
        self._ids = itertools.count(1)
        router.post(f"{url}/Users/AuthenticateByName").mock(side_effect=self._authenticate)
        router.get(f"{url}/Items").mock(side_effect=self._items)
        router.post(f"{url}/Sessions/Logout").mock(side_effect=self._logout)

    def add_user(self, name: str, password: str) -> None:
        self.passwords[name] = password
        self.played[name] = []

    def add_series(self, provider_ids: dict[str, str]) -> str:
        series_id = f"series{next(self._ids)}"
        self.series[series_id] = {"Id": series_id, "Type": "Series", "ProviderIds": provider_ids}
        return series_id

    def play_movie(self, user: str, provider_ids: dict[str, str], at: dt.datetime | None) -> None:
        self._play(user, {"Type": "Movie", "ProviderIds": provider_ids}, at)

    def play_episode(self, user: str, series_id: str, season: int, episode: int, at: dt.datetime | None) -> None:
        item = {"Type": "Episode", "SeriesId": series_id, "ParentIndexNumber": season, "IndexNumber": episode}
        self._play(user, {**item, "ProviderIds": {}}, at)

    def revoke_tokens(self) -> None:
        self.tokens.clear()

    def _play(self, user: str, item: dict, at: dt.datetime | None) -> None:
        last_played = None if at is None else at.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
        self.played[user].append(
            {**item, "Id": f"item{next(self._ids)}", "UserData": {"Played": True, "LastPlayedDate": last_played}}
        )

    def _authorization(self, request: httpx.Request) -> dict[str, str]:
        header = request.headers.get("Authorization", "").removeprefix("MediaBrowser ")
        fields = (field.strip().split("=", 1) for field in header.split(","))
        return {key: value.strip('"') for key, value in fields}

    def _user(self, request: httpx.Request) -> str | None:
        self.requests.append(request)
        return self.tokens.get(self._authorization(request).get("Token", ""))

    def _authenticate(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if self.passwords.get(body["Username"]) != body["Pw"]:
            return httpx.Response(401)
        device = self._authorization(request)["DeviceId"]
        # Jellyfin ends the earlier session of the same user on the same device.
        for token, owner in list(self.tokens.items()):
            if owner == body["Username"] and self.devices[token] == device:
                del self.tokens[token]
        token = secrets.token_hex(16)
        self.tokens[token] = body["Username"]
        self.devices[token] = device
        user = {"Id": f"user-{body['Username']}", "Name": body["Username"]}
        return httpx.Response(200, json={"AccessToken": token, "ServerId": SERVER_ID, "User": user})

    def _items(self, request: httpx.Request) -> httpx.Response:
        user = self._user(request)
        if user is None:
            return httpx.Response(401)
        params = request.url.params
        if "Ids" in params:
            items = [self.series[item_id] for item_id in params["Ids"].split(",") if item_id in self.series]
            return httpx.Response(200, json={"Items": items, "TotalRecordCount": len(items)})
        played = sorted(self.played[user], key=lambda item: item["UserData"]["LastPlayedDate"] or "", reverse=True)
        start, limit = int(params["StartIndex"]), int(params["Limit"])
        return httpx.Response(200, json={"Items": played[start : start + limit], "TotalRecordCount": len(played)})

    def _logout(self, request: httpx.Request) -> httpx.Response:
        if self._user(request) is None:
            return httpx.Response(401)
        del self.tokens[self._authorization(request)["Token"]]
        return httpx.Response(204)


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> collections.abc.Generator[str]:
    """A configured secret key, which encrypts the stored Jellyfin tokens."""
    monkeypatch.setenv("MINTRACK__SECURITY__SECRET_KEY", SECRET_KEY)
    get_config.cache_clear()
    yield SECRET_KEY
    monkeypatch.undo()
    get_config.cache_clear()


@pytest.fixture
def jellyfin(respx_mock: respx.Router, secret_key: str) -> FakeJellyfin:
    return FakeJellyfin(respx_mock)
