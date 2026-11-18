import typing
import uuid

import fastapi
import pydantic

from mintrack.core.accounts.managers import (
    AccountManager,
    InvalidCredentialsError,
    LoginRateLimitedError,
    available_timezones,
)
from mintrack.core.accounts.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import (
    XSRF_COOKIE,
    CurrentSessionDepType,
    CurrentUserDepType,
    clear_session_cookie,
    set_session_cookies,
    set_xsrf_cookie,
    utc_now,
)

INVALID_LINK = "This link is invalid or has expired."

# Login and the password-link endpoints need no session; the other routes are mounted behind it.
public_router = fastapi.APIRouter(prefix="/auth", tags=["auth"])
router = fastapi.APIRouter(prefix="/auth", tags=["auth"])


def _check_timezone(value: str) -> str:
    if value not in available_timezones():
        msg = "must be an IANA time zone such as Europe/Paris"
        raise ValueError(msg)
    return value


Timezone = typing.Annotated[str, pydantic.AfterValidator(_check_timezone)]
NewPassword = typing.Annotated[str, pydantic.Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
AnyPassword = typing.Annotated[str, pydantic.Field(max_length=PASSWORD_MAX_LENGTH)]
Token = typing.Annotated[str, pydantic.Field(max_length=128)]


class UserResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    is_admin: bool
    timezone: str


class LoginRequest(pydantic.BaseModel):
    username: typing.Annotated[str, pydantic.Field(max_length=150)]
    password: AnyPassword


class LinkRequest(pydantic.BaseModel):
    token: Token


class LinkResponse(pydantic.BaseModel):
    username: str


class UseLinkRequest(pydantic.BaseModel):
    token: Token
    password: NewPassword
    timezone: Timezone | None = None


class UpdateMeRequest(pydantic.BaseModel):
    timezone: Timezone


class ChangePasswordRequest(pydantic.BaseModel):
    current_password: AnyPassword
    new_password: NewPassword


def _client_address(request: fastapi.Request) -> str:
    return request.client.host if request.client else "unknown"


@public_router.post(
    "/login",
    responses={
        fastapi.status.HTTP_401_UNAUTHORIZED: {"description": "Wrong username or password"},
        fastapi.status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many failed logins"},
    },
)
async def login(
    body: LoginRequest, request: fastapi.Request, response: fastapi.Response, db: DbSessionDepType
) -> UserResponse:
    try:
        user, token = await AccountManager(db).login(
            body.username, body.password, address=_client_address(request), now=utc_now()
        )
    except LoginRateLimitedError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed logins, try again in a few minutes"
        ) from None
    except InvalidCredentialsError:
        # The failure is recorded for the rate limit.
        await db.commit()
        raise fastapi.HTTPException(fastapi.status.HTTP_401_UNAUTHORIZED, "Wrong username or password") from None
    await db.commit()
    set_session_cookies(response, token)
    return UserResponse.model_validate(user)


@public_router.post("/password-link", responses={fastapi.status.HTTP_400_BAD_REQUEST: {"description": INVALID_LINK}})
async def describe_password_link(body: LinkRequest, db: DbSessionDepType) -> LinkResponse:
    user = await AccountManager(db).find_link_user(body.token, now=utc_now())
    if user is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_400_BAD_REQUEST, INVALID_LINK)
    return LinkResponse(username=user.username)


@public_router.post(
    "/password-link/use", responses={fastapi.status.HTTP_400_BAD_REQUEST: {"description": INVALID_LINK}}
)
async def use_password_link(body: UseLinkRequest, response: fastapi.Response, db: DbSessionDepType) -> UserResponse:
    manager = AccountManager(db)
    now = utc_now()
    user = await manager.use_link(body.token, body.password, timezone=body.timezone, now=now)
    if user is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_400_BAD_REQUEST, INVALID_LINK)
    token = await manager.create_session(user, now=now)
    await db.commit()
    set_session_cookies(response, token)
    return UserResponse.model_validate(user)


@router.get("/me")
async def me(user: CurrentUserDepType, request: fastapi.Request, response: fastapi.Response) -> UserResponse:
    if XSRF_COOKIE not in request.cookies:
        set_xsrf_cookie(response)
    return UserResponse.model_validate(user)


@router.patch("/me")
async def update_me(body: UpdateMeRequest, user: CurrentUserDepType, db: DbSessionDepType) -> UserResponse:
    user.timezone = body.timezone
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def logout(current: CurrentSessionDepType, response: fastapi.Response, db: DbSessionDepType) -> None:
    await AccountManager(db).delete_session(current.session_id)
    await db.commit()
    clear_session_cookie(response)


@router.post("/logout-all", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def logout_all(current: CurrentSessionDepType, response: fastapi.Response, db: DbSessionDepType) -> None:
    await AccountManager(db).delete_sessions(current.user.id)
    await db.commit()
    clear_session_cookie(response)


@router.post(
    "/password",
    status_code=fastapi.status.HTTP_204_NO_CONTENT,
    responses={fastapi.status.HTTP_400_BAD_REQUEST: {"description": "Wrong current password"}},
)
async def change_password(body: ChangePasswordRequest, current: CurrentSessionDepType, db: DbSessionDepType) -> None:
    try:
        await AccountManager(db).change_password(
            current.user, body.current_password, body.new_password, keep_session=current.session_id
        )
    except InvalidCredentialsError:
        raise fastapi.HTTPException(fastapi.status.HTTP_400_BAD_REQUEST, "Wrong current password") from None
    await db.commit()
