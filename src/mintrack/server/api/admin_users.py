import datetime as dt
import typing
import uuid

import fastapi
import pydantic

from mintrack.config import get_config
from mintrack.core.accounts.managers import (
    USERNAME_PATTERN,
    AccountManager,
    LastAdminError,
    UserDisabledError,
    UsernameTakenError,
    UserStatus,
    user_status,
)
from mintrack.core.accounts.tokens import password_link
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import User
from mintrack.server.api.dependencies import CurrentUserDepType, get_admin_user, utc_now

router = fastapi.APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[fastapi.Depends(get_admin_user)])


class AdminUserResponse(pydantic.BaseModel):
    id: uuid.UUID
    username: str
    is_admin: bool
    status: UserStatus
    last_seen_at: dt.datetime | None


class CreateUserRequest(pydantic.BaseModel):
    username: typing.Annotated[str, pydantic.Field(pattern=USERNAME_PATTERN)]


class LinkResponse(pydantic.BaseModel):
    """A password link, shown once: only its hash is stored."""

    link: str


class CreatedUserResponse(LinkResponse):
    user: AdminUserResponse


class UpdateUserRequest(pydantic.BaseModel):
    is_active: bool


def _describe(user: User, last_seen_at: dt.datetime | None = None) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        status=user_status(user, utc_now()),
        last_seen_at=last_seen_at,
    )


async def _get_user(db: DbSessionDepType, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "No such user")
    return user


@router.get("")
async def list_users(db: DbSessionDepType) -> list[AdminUserResponse]:
    return [_describe(user, last_seen_at) for user, last_seen_at in await AccountManager(db).list_users()]


@router.post(
    "",
    status_code=fastapi.status.HTTP_201_CREATED,
    responses={fastapi.status.HTTP_409_CONFLICT: {"description": "Username taken"}},
)
async def create_user(body: CreateUserRequest, db: DbSessionDepType) -> CreatedUserResponse:
    try:
        user, token = await AccountManager(db).create_user(body.username, is_admin=False, now=utc_now())
    except UsernameTakenError:
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, "This username is taken") from None
    await db.commit()
    return CreatedUserResponse(user=_describe(user), link=password_link(get_config().project.public_origin, token))


@router.post(
    "/{user_id}/link",
    responses={
        fastapi.status.HTTP_404_NOT_FOUND: {"description": "No such user"},
        fastapi.status.HTTP_409_CONFLICT: {"description": "Disabled user"},
    },
)
async def create_link(user_id: uuid.UUID, db: DbSessionDepType) -> LinkResponse:
    user = await _get_user(db, user_id)
    try:
        token = AccountManager.issue_link(user, now=utc_now())
    except UserDisabledError:
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, "Enable this user first") from None
    await db.commit()
    return LinkResponse(link=password_link(get_config().project.public_origin, token))


@router.patch(
    "/{user_id}",
    responses={
        fastapi.status.HTTP_404_NOT_FOUND: {"description": "No such user"},
        fastapi.status.HTTP_409_CONFLICT: {"description": "Last active admin, or the admin's own account"},
    },
)
async def update_user(
    user_id: uuid.UUID, body: UpdateUserRequest, db: DbSessionDepType, admin: CurrentUserDepType
) -> AdminUserResponse:
    user = await _get_user(db, user_id)
    if user.id == admin.id and not body.is_active:
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, "You cannot disable your own account")
    try:
        await AccountManager(db).set_active(user, active=body.is_active)
    except LastAdminError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_409_CONFLICT, "The last active admin cannot be disabled"
        ) from None
    await db.commit()
    return _describe(user)
