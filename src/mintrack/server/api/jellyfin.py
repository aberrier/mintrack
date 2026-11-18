import datetime as dt
import enum
import uuid

import fastapi
import pydantic

from mintrack.core.jellyfin.managers import JellyfinManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import JellyfinAccount, JellyfinSyncStatus, User
from mintrack.integrations.jellyfin.client import (
    ForbiddenAddressError,
    JellyfinError,
    JellyfinRedirectError,
    JellyfinUnauthorizedError,
    JellyfinUnreachableError,
)
from mintrack.server.api.dependencies import CurrentUserDepType
from mintrack.worker.tasks import defer_jellyfin_sync

router = fastapi.APIRouter(prefix="/jellyfin/accounts", tags=["jellyfin"])


class LinkError(enum.StrEnum):
    INVALID_CREDENTIALS = "jellyfin_invalid_credentials"
    FORBIDDEN_ADDRESS = "jellyfin_forbidden_address"
    UNREACHABLE = "jellyfin_unreachable"
    REDIRECTED = "jellyfin_redirected"
    BAD_RESPONSE = "jellyfin_bad_response"


class LinkErrorResponse(pydantic.BaseModel):
    detail: LinkError


class LinkRequest(pydantic.BaseModel):
    server_url: pydantic.HttpUrl
    username: str = pydantic.Field(min_length=1)
    password: pydantic.SecretStr

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


def link_error(error: JellyfinError) -> fastapi.HTTPException:
    match error:
        case JellyfinUnauthorizedError():
            status, detail = fastapi.status.HTTP_400_BAD_REQUEST, LinkError.INVALID_CREDENTIALS
        case ForbiddenAddressError():
            status, detail = fastapi.status.HTTP_400_BAD_REQUEST, LinkError.FORBIDDEN_ADDRESS
        case JellyfinUnreachableError():
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


@router.get("")
async def list_accounts(user: CurrentUserDepType, session: DbSessionDepType) -> list[JellyfinAccountResponse]:
    accounts = await JellyfinManager(session).list_for_user(user)
    return [JellyfinAccountResponse.model_validate(account) for account in accounts]


@router.post(
    "",
    status_code=fastapi.status.HTTP_201_CREATED,
    responses={
        fastapi.status.HTTP_400_BAD_REQUEST: {"model": LinkErrorResponse},
        fastapi.status.HTTP_502_BAD_GATEWAY: {"model": LinkErrorResponse},
    },
)
async def link_account(
    request: LinkRequest, user: CurrentUserDepType, session: DbSessionDepType
) -> JellyfinAccountResponse:
    try:
        account = await JellyfinManager(session).link(
            user, request.server_base_url, request.username, request.password.get_secret_value()
        )
    except JellyfinError as error:
        raise link_error(error) from None
    await defer_jellyfin_sync(session, account.id, account.user_id)
    await session.commit()
    return JellyfinAccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def unlink_account(account_id: uuid.UUID, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    manager = JellyfinManager(session)
    await manager.unlink(await get_account(manager, user, account_id))


@router.post("/{account_id}/sync", status_code=fastapi.status.HTTP_202_ACCEPTED)
async def sync_account(account_id: uuid.UUID, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    account = await get_account(JellyfinManager(session), user, account_id)
    await defer_jellyfin_sync(session, account.id, account.user_id, full=True)
    await session.commit()
