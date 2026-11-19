import asyncio
import collections.abc
import datetime as dt
import ipaddress
import socket
import types
import typing
import urllib.parse
import uuid

import httpx
import pydantic
from pydantic.alias_generators import to_pascal

from mintrack.config import get_config

PAGE_SIZE = 500
IDS_PER_REQUEST = 100
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
# Across the requests of one client: a sync reads far less from a real server.
MAX_TOTAL_BYTES = 200 * 1024 * 1024
TIMEOUT = httpx.Timeout(10, read=60)
# Whole request, body included: a server sending a byte now and then never hits the read timeout.
TOTAL_TIMEOUT_SECONDS = 120
type Params = dict[str, str | int]
type Json = dict[str, str]

# Cloud metadata services outside the link-local range.
METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(address) for address in ("100.100.100.200", "168.63.129.16", "fd00:ec2::254")
)


class JellyfinError(Exception):
    """Jellyfin answered something unexpected."""


class JellyfinUnreachableError(JellyfinError):
    """The server cannot be reached, timed out or failed (5xx)."""


class JellyfinUnauthorizedError(JellyfinError):
    """Wrong credentials, or the token was revoked."""


class JellyfinRedirectError(JellyfinError):
    """The server redirected the request: its address is another one."""


class QuickConnectDisabledError(JellyfinError):
    """The server has Quick Connect turned off: the account is linked with a password instead."""


class ForbiddenAddressError(JellyfinError):
    """The server address is one no media server lives at (link-local, cloud metadata...)."""


class _Payload(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(alias_generator=to_pascal, extra="ignore")


# Text from the server, stored or shown: bounded, and without NUL, which PostgreSQL text cannot hold.
Text = typing.Annotated[str, pydantic.StringConstraints(max_length=512, pattern=r"^[^\x00]*$")]
# The provider ids matching uses; a server may send any number of others.
PROVIDERS = frozenset({"Tmdb", "Imdb", "Tvdb"})


class PublicSystemInfo(_Payload):
    id: Text
    version: Text


class JellyfinUser(_Payload):
    id: Text
    name: Text


class Authentication(_Payload):
    access_token: Text
    server_id: Text
    user: JellyfinUser


class QuickConnect(_Payload):
    secret: Text
    code: Text
    authenticated: bool = False


class UserData(_Payload):
    last_played_date: dt.datetime | None = None


class Item(_Payload):
    id: Text
    type: Text
    name: Text = ""
    original_title: Text | None = None
    # Sent without asking, like the names and numbers; the other fields come through `Fields`.
    production_year: int | None = None
    provider_ids: dict[str, Text | None] = {}
    series_id: Text | None = None
    series_name: Text | None = None
    parent_index_number: int | None = None
    index_number: int | None = None
    user_data: UserData = UserData()

    @pydantic.field_validator("provider_ids", mode="wrap")
    @classmethod
    def _known_providers(cls, value: object, handler: pydantic.ValidatorFunctionWrapHandler) -> dict[str, str | None]:
        if isinstance(value, dict):
            value = {key: id_ for key, id_ in value.items() if key in PROVIDERS}
        return handler(value)


class ItemsPage(_Payload):
    items: list[Item]
    total_record_count: int


def is_forbidden_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return (
        address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or (address.is_reserved and not address.is_loopback)
        or address in METADATA_ADDRESSES
    )


async def check_address(url: httpx.URL) -> str:
    """Refuse a host that resolves to an address no media server lives at; private and loopback ones are fine.

    Returns the address to connect to: connecting to the checked address, rather than resolving the name again,
    keeps a name that changes its answer between the two (DNS rebinding) from reaching a forbidden address.
    """
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(url.host, url.port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as error:
        raise JellyfinUnreachableError from error
    addresses = [ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0]) for *_, sockaddr in infos]
    if not addresses:
        raise JellyfinUnreachableError
    if any(is_forbidden_address(address) for address in addresses):
        raise ForbiddenAddressError
    return str(addresses[0])


class JellyfinClient:
    """The few Jellyfin REST calls MinTrack needs, as one user of one server."""

    def __init__(self, server_url: str, *, device_id: uuid.UUID, token: str | None = None) -> None:
        version = get_config().project.version
        authorization = (
            f'MediaBrowser Client="MinTrack", Device="MinTrack", DeviceId="{device_id}", Version="{version}"'
        )
        if token is not None:
            authorization += f', Token="{token}"'
        self._http = httpx.AsyncClient(
            base_url=server_url,
            timeout=TIMEOUT,
            headers={"Authorization": authorization, "Accept": "application/json"},
        )
        self._host = self._http.base_url.host
        self._read_bytes = 0

    async def __aenter__(self) -> typing.Self:
        url = self._http.base_url
        address = await check_address(url)
        # Requests go to the checked address, under the server's name (Host header, TLS name and certificate).
        self._host = url.host
        self._http.headers["Host"] = url.netloc.decode("ascii")
        self._http.base_url = url.copy_with(host=address)
        await self._http.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        await self._http.__aexit__(exc_type, exc, traceback)

    async def _request(
        self, method: str, path: str, *, params: Params | None = None, json: Json | None = None
    ) -> bytes:
        try:
            async with (
                asyncio.timeout(TOTAL_TIMEOUT_SECONDS),
                self._http.stream(
                    method, path, params=params, json=json, extensions={"sni_hostname": self._host}
                ) as response,
            ):
                if response.status_code in {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}:
                    raise JellyfinUnauthorizedError
                if response.is_server_error:
                    raise JellyfinUnreachableError(response.status_code)
                if response.is_redirect:
                    raise JellyfinRedirectError(response.status_code)
                if not response.is_success:
                    raise JellyfinError(response.status_code)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    self._read_bytes += len(chunk)
                    if len(body) > MAX_RESPONSE_BYTES or self._read_bytes > MAX_TOTAL_BYTES:
                        msg = "response too large"
                        raise JellyfinError(msg)
                return bytes(body)
        except (httpx.TransportError, TimeoutError) as error:
            raise JellyfinUnreachableError from error

    async def _get_json[T: pydantic.BaseModel](
        self, model: type[T], method: str, path: str, *, params: Params | None = None, json: Json | None = None
    ) -> T:
        try:
            return model.model_validate_json(await self._request(method, path, params=params, json=json))
        except pydantic.ValidationError as error:
            raise JellyfinError from error

    async def check_server(self) -> None:
        """Raise `JellyfinUnreachableError` unless a Jellyfin server answers: until one does, every failure looks the
        same, so the answers tell nothing about what else listens at an address."""
        try:
            await self._get_json(PublicSystemInfo, "GET", "/System/Info/Public")
        except JellyfinError as error:
            raise JellyfinUnreachableError from error

    async def authenticate(self, username: str, password: str) -> Authentication:
        payload = {"Username": username, "Pw": password}
        return await self._get_json(Authentication, "POST", "/Users/AuthenticateByName", json=payload)

    async def quick_connect_enabled(self) -> bool:
        try:
            return pydantic.TypeAdapter(bool).validate_json(await self._request("GET", "/QuickConnect/Enabled"))
        except pydantic.ValidationError as error:
            raise JellyfinError from error

    async def initiate_quick_connect(self) -> QuickConnect:
        """A new Quick Connect request of this device: its code, to approve in a Jellyfin app, and its secret."""
        return await self._get_json(QuickConnect, "POST", "/QuickConnect/Initiate")

    async def quick_connect(self, secret: str) -> QuickConnect:
        """The state of a Quick Connect request."""
        return await self._get_json(QuickConnect, "GET", "/QuickConnect/Connect", params={"secret": secret})

    async def authenticate_with_quick_connect(self, secret: str) -> Authentication:
        """Exchange an approved Quick Connect request for a token, as the user who approved it."""
        payload = {"Secret": secret}
        return await self._get_json(Authentication, "POST", "/Users/AuthenticateWithQuickConnect", json=payload)

    async def played_items(self, user_id: str, start_index: int) -> ItemsPage:
        """Played movies and episodes, last played first."""
        params = {
            "userId": user_id,
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Episode",
            "Filters": "IsPlayed",
            "Fields": "ProviderIds,OriginalTitle",
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
            "EnableImages": "false",
            "StartIndex": start_index,
            "Limit": PAGE_SIZE,
        }
        return _at_most(await self._get_json(ItemsPage, "GET", "/Items", params=params), PAGE_SIZE)

    async def items(self, user_id: str, ids: collections.abc.Collection[str]) -> list[Item]:
        """The items with these ids, with their provider ids."""
        ids = sorted(ids)
        found: list[Item] = []
        for start in range(0, len(ids), IDS_PER_REQUEST):
            params: Params = {
                "userId": user_id,
                "Ids": ",".join(ids[start : start + IDS_PER_REQUEST]),
                "Fields": "ProviderIds,OriginalTitle",
            }
            page = await self._get_json(ItemsPage, "GET", "/Items", params=params)
            found.extend(_at_most(page, IDS_PER_REQUEST).items)
        return found

    async def season_numbers(self, user_id: str, series_id: str) -> list[int]:
        """The numbers of a series' seasons with files, 0 for its specials."""
        path = f"/Shows/{urllib.parse.quote(series_id, safe='')}/Seasons"
        # Seasons only known from the metadata, with no episode on the server, are left out.
        params: Params = {"userId": user_id, "isMissing": "false"}
        page = await self._get_json(ItemsPage, "GET", path, params=params)
        return [season.index_number for season in page.items if season.index_number is not None]

    async def logout(self) -> None:
        await self._request("POST", "/Sessions/Logout")


def _at_most(page: ItemsPage, limit: int) -> ItemsPage:
    if len(page.items) > limit:
        msg = f"more items than the {limit} asked for"
        raise JellyfinError(msg)
    return page
