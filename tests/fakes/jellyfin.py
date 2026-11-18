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
        router.get(f"{url}/System/Info/Public").mock(side_effect=self._public_info)
        # False: another server answers at the address.
        self.is_jellyfin = True
        router.post(f"{url}/Users/AuthenticateByName").mock(side_effect=self._authenticate)
        router.get(f"{url}/Items").mock(side_effect=self._items)
        router.post(f"{url}/Sessions/Logout").mock(side_effect=self._logout)
        router.get(f"{url}/QuickConnect/Enabled").mock(
            side_effect=lambda _: httpx.Response(200, json=self.quick_connect)
        )
        router.post(f"{url}/QuickConnect/Initiate").mock(side_effect=self._initiate)
        router.get(f"{url}/QuickConnect/Connect").mock(side_effect=self._connect)
        router.post(f"{url}/Users/AuthenticateWithQuickConnect").mock(side_effect=self._authenticate_with_quick_connect)
        self.quick_connect = True
        # Quick Connect requests: secret -> (code, device, user who approved it).
        self.quick_connect_requests: dict[str, tuple[str, str, str | None]] = {}

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
        return self._session(body["Username"], self._authorization(request)["DeviceId"])

    def _session(self, name: str, device: str) -> httpx.Response:
        # Jellyfin ends the earlier session of the same user on the same device.
        for token, owner in list(self.tokens.items()):
            if owner == name and self.devices[token] == device:
                del self.tokens[token]
        token = secrets.token_hex(16)
        self.tokens[token] = name
        self.devices[token] = device
        user = {"Id": f"user-{name}", "Name": name}
        return httpx.Response(200, json={"AccessToken": token, "ServerId": SERVER_ID, "User": user})

    def approve(self, code: str, user: str) -> None:
        """The user enters the code in a Jellyfin app."""
        for secret, (request_code, device, _) in self.quick_connect_requests.items():
            if request_code == code:
                self.quick_connect_requests[secret] = (request_code, device, user)

    def _initiate(self, request: httpx.Request) -> httpx.Response:
        if not self.quick_connect:
            return httpx.Response(401)
        secret, code = secrets.token_hex(16), f"{secrets.randbelow(10**6):06}"
        self.quick_connect_requests[secret] = (code, self._authorization(request)["DeviceId"], None)
        return httpx.Response(200, json={"Secret": secret, "Code": code, "Authenticated": False})

    def _connect(self, request: httpx.Request) -> httpx.Response:
        secret = request.url.params["secret"]
        if secret not in self.quick_connect_requests:
            return httpx.Response(404)
        code, _, user = self.quick_connect_requests[secret]
        return httpx.Response(200, json={"Secret": secret, "Code": code, "Authenticated": user is not None})

    def _authenticate_with_quick_connect(self, request: httpx.Request) -> httpx.Response:
        secret = json.loads(request.content)["Secret"]
        _, device, user = self.quick_connect_requests.get(secret, ("", "", None))
        # Jellyfin only answers the device that started the request.
        if user is None or device != self._authorization(request)["DeviceId"]:
            return httpx.Response(401)
        del self.quick_connect_requests[secret]
        return self._session(user, device)

    def _public_info(self, _: httpx.Request) -> httpx.Response:
        if not self.is_jellyfin:
            return httpx.Response(404, text="<html>Not found</html>")
        return httpx.Response(200, json={"Id": SERVER_ID, "Version": "10.11.0", "ProductName": "Jellyfin Server"})

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
