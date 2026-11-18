import collections
import datetime as dt
import enum
import time
import typing
import uuid

import fastapi
import pydantic

from mintrack.core.jellyfin.managers import JellyfinManager, QuickConnectPendingError
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import JellyfinAccount, JellyfinSyncStatus, User
from mintrack.integrations.jellyfin.client import (
    ForbiddenAddressError,
    JellyfinError,
    JellyfinRedirectError,
    JellyfinUnauthorizedError,
    JellyfinUnreachableError,
    QuickConnectDisabledError,
)
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(prefix="/jellyfin", tags=["jellyfin"])

# Requests to a server address per user and minute: a Quick Connect wait polls every 3 seconds.
SERVER_REQUESTS_PER_MINUTE = 30
_server_requests: collections.defaultdict[uuid.UUID, collections.deque[float]] = collections.defaultdict(
    collections.deque
)

ServerUrl = typing.Annotated[pydantic.HttpUrl, pydantic.UrlConstraints(max_length=2048)]
QuickConnectSecret = typing.Annotated[str, pydantic.Field(min_length=1, max_length=256)]


class LinkError(enum.StrEnum):
    INVALID_CREDENTIALS = "jellyfin_invalid_credentials"
    UNREACHABLE = "jellyfin_unreachable"
    REDIRECTED = "jellyfin_redirected"
    BAD_RESPONSE = "jellyfin_bad_response"
    QUICK_CONNECT_DISABLED = "jellyfin_quick_connect_disabled"
    QUICK_CONNECT_PENDING = "jellyfin_quick_connect_pending"


class LinkErrorResponse(pydantic.BaseModel):
    detail: LinkError


class JellyfinServerRequest(pydantic.BaseModel):
    server_url: ServerUrl

    @pydantic.field_validator("server_url")
    @classmethod
    def _no_credentials_query_or_fragment(cls, value: pydantic.HttpUrl) -> pydantic.HttpUrl:
        if value.username or value.password or value.query or value.fragment:
            msg = "must be the server address, without credentials, query or fragment"
            raise ValueError(msg)
        return value

    @property
    def server_base_url(self) -> str:
        return str(self.server_url).rstrip("/")


class JellyfinLinkRequest(JellyfinServerRequest):
    username: str = pydantic.Field(min_length=1, max_length=256)
    password: pydantic.SecretStr = pydantic.Field(max_length=1024)


class QuickConnectRequest(JellyfinServerRequest):
    secret: QuickConnectSecret


class QuickConnectResponse(pydantic.BaseModel):
    # Shown to the user, who enters it in a Jellyfin app signed in to their account.
    code: str
    # Sent back to poll the request and to link the account once approved.
    secret: str


class QuickConnectStateResponse(pydantic.BaseModel):
    approved: bool


class JellyfinAccountResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_url: str
    username: str
    last_sync_at: dt.datetime | None
    last_success_at: dt.datetime | None
    last_sync_status: JellyfinSyncStatus | None
    last_sync_imported: int
    last_sync_skipped: int


LINK_ERRORS: dict[int | str, dict[str, typing.Any]] = {
    fastapi.status.HTTP_400_BAD_REQUEST: {"model": LinkErrorResponse},
    fastapi.status.HTTP_502_BAD_GATEWAY: {"model": LinkErrorResponse},
    fastapi.status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many requests to server addresses"},
}


def link_error(error: JellyfinError) -> fastapi.HTTPException:
    match error:
        case JellyfinUnauthorizedError():
            status, detail = fastapi.status.HTTP_400_BAD_REQUEST, LinkError.INVALID_CREDENTIALS
        case QuickConnectDisabledError():
            status, detail = fastapi.status.HTTP_400_BAD_REQUEST, LinkError.QUICK_CONNECT_DISABLED
        # A forbidden address answers as an unreachable one, so the errors tell nothing about the network.
        case ForbiddenAddressError() | JellyfinUnreachableError():
            status, detail = fastapi.status.HTTP_502_BAD_GATEWAY, LinkError.UNREACHABLE
        case JellyfinRedirectError():
            status, detail = fastapi.status.HTTP_502_BAD_GATEWAY, LinkError.REDIRECTED
        case _:
            status, detail = fastapi.status.HTTP_502_BAD_GATEWAY, LinkError.BAD_RESPONSE
    return fastapi.HTTPException(status_code=status, detail=detail)


async def get_account(manager: JellyfinManager, user: User, account_id: uuid.UUID) -> JellyfinAccount:
    account = await manager.get_for_user(user, account_id)
    if account is None:
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND)
    return account


def limit_server_requests(user: CurrentUserDepType) -> None:
    """Refuse a user's requests to server addresses beyond the rate: they would probe the network around MinTrack."""
    now, recent = time.monotonic(), _server_requests[user.id]
    while recent and recent[0] <= now - 60:
        recent.popleft()
    if len(recent) >= SERVER_REQUESTS_PER_MINUTE:
        raise fastapi.HTTPException(fastapi.status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, try again later")
    recent.append(now)


LIMITED = [fastapi.Depends(limit_server_requests)]


@router.get("/accounts")
async def list_accounts(user: CurrentUserDepType, session: DbSessionDepType) -> list[JellyfinAccountResponse]:
    accounts = await JellyfinManager(session).list_for_user(user)
    return [JellyfinAccountResponse.model_validate(account) for account in accounts]


@router.post("/accounts", status_code=fastapi.status.HTTP_201_CREATED, responses=LINK_ERRORS, dependencies=LIMITED)
async def link_account(
    request: JellyfinLinkRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> JellyfinAccountResponse:
    """Link with a username and password, for servers without Quick Connect; the password is not stored."""
    try:
        account = await JellyfinManager(session).link(
            user, request.server_base_url, request.username, request.password.get_secret_value()
        )
    except JellyfinError as error:
        raise link_error(error) from None
    return JellyfinAccountResponse.model_validate(account)


@router.post("/quick-connect", responses=LINK_ERRORS, dependencies=LIMITED)
async def start_quick_connect(
    request: JellyfinServerRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> QuickConnectResponse:
    """Start a Quick Connect request: the user approves its code in a Jellyfin app, then the account is linked."""
    try:
        quick_connect = await JellyfinManager(session).start_quick_connect(user, request.server_base_url)
    except JellyfinError as error:
        raise link_error(error) from None
    return QuickConnectResponse(code=quick_connect.code, secret=quick_connect.secret)


@router.post("/quick-connect/state", responses=LINK_ERRORS, dependencies=LIMITED)
async def quick_connect_state(
    request: QuickConnectRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> QuickConnectStateResponse:
    """Whether the user approved the Quick Connect request yet."""
    try:
        approved = await JellyfinManager(session).quick_connect_approved(user, request.server_base_url, request.secret)
    except JellyfinError as error:
        raise link_error(error) from None
    return QuickConnectStateResponse(approved=approved)


@router.post(
    "/accounts/quick-connect",
    status_code=fastapi.status.HTTP_201_CREATED,
    responses={**LINK_ERRORS, fastapi.status.HTTP_409_CONFLICT: {"model": LinkErrorResponse}},
    dependencies=LIMITED,
)
async def link_quick_connect_account(
    request: QuickConnectRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> JellyfinAccountResponse:
    """Link the account of the user who approved the Quick Connect request; 409 while it is not approved."""
    try:
        account = await JellyfinManager(session).link_quick_connect(user, request.server_base_url, request.secret)
    except QuickConnectPendingError:
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, LinkError.QUICK_CONNECT_PENDING) from None
    except JellyfinError as error:
        raise link_error(error) from None
    return JellyfinAccountResponse.model_validate(account)


@router.delete("/accounts/{account_id}", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unlink_account(account_id: uuid.UUID, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    manager = JellyfinManager(session)
    await manager.unlink(await get_account(manager, user, account_id))


@router.post("/accounts/{account_id}/sync", status_code=fastapi.status.HTTP_202_ACCEPTED)
async def sync_account(account_id: uuid.UUID, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    manager = JellyfinManager(session)
    await manager.request_sync(await get_account(manager, user, account_id), full=True)
