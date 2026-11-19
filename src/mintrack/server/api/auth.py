import datetime as dt
import typing
import uuid

import fastapi
import fastapi.responses
import pydantic

from mintrack.core.accounts.devices import device_label
from mintrack.core.accounts.managers import (
    USERNAME_PATTERN,
    AccountManager,
    InvalidCredentialsError,
    LinkProblem,
    LoginRateLimitedError,
    SetupClosedError,
    available_timezones,
    database_timezone,
    timezone_choices,
)
from mintrack.core.accounts.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import (
    WITHOUT_NUL,
    XSRF_COOKIE,
    CurrentSessionDepType,
    CurrentUserDepType,
    clear_session_cookie,
    set_session_cookies,
    set_xsrf_cookie,
    utc_now,
)

LINK_PROBLEMS = {
    LinkProblem.INVALID: "This link is not valid. Ask your admin for a new one.",
    LinkProblem.EXPIRED: "This link has expired. Ask your admin for a new one.",
    LinkProblem.USED: "This link was already used. Log in with your password, or ask your admin for a new link.",
    LinkProblem.REPLACED: "A newer link replaced this one. Open the latest link, or ask your admin for a new one.",
}
SETUP_CLOSED = "The admin account already exists."
RATE_LIMITED = "Too many failed logins, try again in a few minutes"

# Login, the first admin's setup and the password-link endpoints need no session; the other routes are mounted
# behind it.
public_router = fastapi.APIRouter(prefix="/auth", tags=["auth"])
router = fastapi.APIRouter(prefix="/auth", tags=["auth"])


TIMEZONE_ERROR = "must be an IANA time zone such as Europe/Paris"


def _check_timezone(value: str) -> str:
    if value not in available_timezones():
        raise ValueError(TIMEZONE_ERROR)
    return value


Timezone = typing.Annotated[str, pydantic.AfterValidator(_check_timezone)]
# The zone a browser reports: one the server does not know is ignored rather than refused.
BrowserTimezone = typing.Annotated[str, pydantic.Field(max_length=64, pattern=WITHOUT_NUL)]
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
    username: typing.Annotated[str, pydantic.Field(max_length=150, pattern=WITHOUT_NUL)]
    password: AnyPassword


class SetupResponse(pydantic.BaseModel):
    open: bool


class SetupRequest(pydantic.BaseModel):
    username: typing.Annotated[str, pydantic.Field(pattern=USERNAME_PATTERN)]
    password: NewPassword
    timezone: BrowserTimezone | None = None


class PasswordLinkRequest(pydantic.BaseModel):
    token: Token


class PasswordLinkResponse(pydantic.BaseModel):
    username: str


class LinkRefusedResponse(pydantic.BaseModel):
    detail: str
    reason: LinkProblem


class UseLinkRequest(pydantic.BaseModel):
    token: Token
    password: NewPassword
    timezone: BrowserTimezone | None = None


class UpdateMeRequest(pydantic.BaseModel):
    timezone: Timezone


class TimezoneResponse(pydantic.BaseModel):
    name: str
    # Older names of the same zone (Asia/Calcutta for Asia/Kolkata), which some browsers still use.
    aliases: list[str]


class SessionResponse(pydantic.BaseModel):
    id: uuid.UUID
    # Such as "Chrome on Android"; null when the browser did not say.
    device: str | None
    last_used_at: dt.datetime
    current: bool


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
            body.username,
            body.password,
            address=_client_address(request),
            now=utc_now(),
            user_agent=request.headers.get("user-agent"),
        )
    except LoginRateLimitedError:
        raise fastapi.HTTPException(fastapi.status.HTTP_429_TOO_MANY_REQUESTS, RATE_LIMITED) from None
    except InvalidCredentialsError:
        # The failure is recorded for the rate limit.
        await db.commit()
        raise fastapi.HTTPException(fastapi.status.HTTP_401_UNAUTHORIZED, "Wrong username or password") from None
    await db.commit()
    set_session_cookies(response, token)
    return UserResponse.model_validate(user)


@public_router.get("/setup")
async def setup_state(db: DbSessionDepType) -> SetupResponse:
    """Whether the first admin can still be created from the browser."""
    return SetupResponse(open=await AccountManager(db).setup_is_open())


@public_router.post(
    "/setup",
    status_code=fastapi.status.HTTP_201_CREATED,
    responses={
        fastapi.status.HTTP_409_CONFLICT: {"description": SETUP_CLOSED},
        fastapi.status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many failed attempts"},
    },
)
async def set_up(
    body: SetupRequest, request: fastapi.Request, response: fastapi.Response, db: DbSessionDepType
) -> UserResponse:
    """Create the first admin, signed in at once; refused as soon as any user exists."""
    manager, now = AccountManager(db), utc_now()
    try:
        user = await manager.create_first_admin(
            body.username, body.password, address=_client_address(request), now=now, timezone=body.timezone
        )
    except LoginRateLimitedError:
        raise fastapi.HTTPException(fastapi.status.HTTP_429_TOO_MANY_REQUESTS, RATE_LIMITED) from None
    except SetupClosedError:
        # The failure is recorded for the rate limit.
        await db.commit()
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, SETUP_CLOSED) from None
    token = await manager.create_session(user, now=now, user_agent=request.headers.get("user-agent"))
    await db.commit()
    set_session_cookies(response, token)
    return UserResponse.model_validate(user)


def _link_refused(problem: LinkProblem) -> fastapi.responses.JSONResponse:
    content = LinkRefusedResponse(detail=LINK_PROBLEMS[problem], reason=problem).model_dump(mode="json")
    return fastapi.responses.JSONResponse(content, status_code=fastapi.status.HTTP_400_BAD_REQUEST)


@public_router.post(
    "/password-link",
    response_model=PasswordLinkResponse,
    responses={fastapi.status.HTTP_400_BAD_REQUEST: {"model": LinkRefusedResponse}},
)
async def describe_password_link(
    body: PasswordLinkRequest, db: DbSessionDepType
) -> PasswordLinkResponse | fastapi.responses.JSONResponse:
    """The account a link sets the password of; only setting the password consumes the link."""
    found = await AccountManager(db).check_link(body.token, now=utc_now())
    if isinstance(found, LinkProblem):
        return _link_refused(found)
    return PasswordLinkResponse(username=found.username)


@public_router.post(
    "/password-link/use",
    response_model=UserResponse,
    responses={fastapi.status.HTTP_400_BAD_REQUEST: {"model": LinkRefusedResponse}},
)
async def use_password_link(
    body: UseLinkRequest, request: fastapi.Request, response: fastapi.Response, db: DbSessionDepType
) -> UserResponse | fastapi.responses.JSONResponse:
    manager = AccountManager(db)
    now = utc_now()
    # A browser's zone PostgreSQL does not know is ignored: the user's default stays.
    timezone = await database_timezone(db, body.timezone) if body.timezone else None
    user = await manager.use_link(body.token, body.password, timezone=timezone, now=now)
    if isinstance(user, LinkProblem):
        return _link_refused(user)
    token = await manager.create_session(user, now=now, user_agent=request.headers.get("user-agent"))
    await db.commit()
    set_session_cookies(response, token)
    return UserResponse.model_validate(user)


@router.get("/me")
async def me(user: CurrentUserDepType, request: fastapi.Request, response: fastapi.Response) -> UserResponse:
    if XSRF_COOKIE not in request.cookies:
        set_xsrf_cookie(response)
    return UserResponse.model_validate(user)


@router.get("/timezones")
async def timezones() -> list[TimezoneResponse]:
    """The time zones a user can choose, UTC first."""
    return [TimezoneResponse(name=name, aliases=aliases) for name, aliases in timezone_choices().items()]


@router.patch("/me", responses={fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Unknown time zone"}})
async def update_me(body: UpdateMeRequest, user: CurrentUserDepType, db: DbSessionDepType) -> UserResponse:
    timezone = await database_timezone(db, body.timezone)
    if timezone is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, f"The time zone {TIMEZONE_ERROR}.")
    user.timezone = timezone
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def logout(current: CurrentSessionDepType, response: fastapi.Response, db: DbSessionDepType) -> None:
    await AccountManager(db).delete_session(current.session_id)
    await db.commit()
    clear_session_cookie(response)


@router.get("/sessions")
async def sessions(current: CurrentSessionDepType, db: DbSessionDepType) -> list[SessionResponse]:
    """The devices signed in to the user's account: this one, then the most recently active first."""
    found = await AccountManager(db).list_sessions(current.user.id, now=utc_now())
    found.sort(key=lambda user_session: user_session.id != current.session_id)
    return [
        SessionResponse(
            id=user_session.id,
            device=device_label(user_session.user_agent),
            last_used_at=user_session.last_used_at,
            current=user_session.id == current.session_id,
        )
        for user_session in found
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=fastapi.status.HTTP_204_NO_CONTENT,
    responses={fastapi.status.HTTP_404_NOT_FOUND: {"description": "No such session"}},
)
async def delete_session(
    session_id: uuid.UUID, current: CurrentSessionDepType, response: fastapi.Response, db: DbSessionDepType
) -> None:
    """Sign out one device, with its notifications."""
    if not await AccountManager(db).delete_user_session(current.user.id, session_id):
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "No such session")
    await db.commit()
    if session_id == current.session_id:
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
