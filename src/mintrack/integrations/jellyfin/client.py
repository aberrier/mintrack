import asyncio
import collections.abc
import datetime as dt
import ipaddress
import socket
import types
import typing
import uuid

import httpx
import pydantic
from pydantic.alias_generators import to_pascal

from mintrack.config import get_config

PAGE_SIZE = 500
IDS_PER_REQUEST = 100
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
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


class ForbiddenAddressError(JellyfinError):
    """The server address is one no media server lives at (link-local, cloud metadata...)."""


class _Payload(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(alias_generator=to_pascal, extra="ignore")


class JellyfinUser(_Payload):
    id: str
    name: str


class Authentication(_Payload):
    access_token: str
    server_id: str
    user: JellyfinUser


class UserData(_Payload):
    last_played_date: dt.datetime | None = None


class Item(_Payload):
    id: str
    type: str
    provider_ids: dict[str, str | None] = {}
    series_id: str | None = None
    parent_index_number: int | None = None
    index_number: int | None = None
    user_data: UserData = UserData()


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


async def check_address(url: httpx.URL) -> None:
    """Refuse a host that resolves to an address no media server lives at; private and loopback ones are fine."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(url.host, url.port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as error:
        raise JellyfinUnreachableError from error
    for *_, sockaddr in infos:
        if is_forbidden_address(ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])):
            raise ForbiddenAddressError


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

    async def __aenter__(self) -> typing.Self:
        await check_address(self._http.base_url)
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
                self._http.stream(method, path, params=params, json=json) as response,
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
                    if len(body) > MAX_RESPONSE_BYTES:
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

    async def authenticate(self, username: str, password: str) -> Authentication:
        payload = {"Username": username, "Pw": password}
        return await self._get_json(Authentication, "POST", "/Users/AuthenticateByName", json=payload)

    async def played_items(self, user_id: str, start_index: int) -> ItemsPage:
        """Played movies and episodes, last played first."""
        params = {
            "userId": user_id,
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Episode",
            "Filters": "IsPlayed",
            "Fields": "ProviderIds",
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
            "EnableImages": "false",
            "StartIndex": start_index,
            "Limit": PAGE_SIZE,
        }
        return await self._get_json(ItemsPage, "GET", "/Items", params=params)

    async def items(self, user_id: str, ids: collections.abc.Collection[str]) -> list[Item]:
        """The items with these ids, with their provider ids."""
        ids = sorted(ids)
        found: list[Item] = []
        for start in range(0, len(ids), IDS_PER_REQUEST):
            params: Params = {
                "userId": user_id,
                "Ids": ",".join(ids[start : start + IDS_PER_REQUEST]),
                "Fields": "ProviderIds",
            }
            found.extend((await self._get_json(ItemsPage, "GET", "/Items", params=params)).items)
        return found

    async def logout(self) -> None:
        await self._request("POST", "/Sessions/Logout")
