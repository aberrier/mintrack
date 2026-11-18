import dataclasses
import datetime as dt
import secrets
import typing
import uuid

import fastapi

from mintrack.config import Config, get_config
from mintrack.core.accounts.managers import SESSION_IDLE_TIMEOUT, AccountManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import User

XSRF_COOKIE = "XSRF-TOKEN"
XSRF_HEADER = "X-XSRF-TOKEN"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _is_https(config: Config) -> bool:
    return config.project.public_url.scheme == "https"


def session_cookie_name(config: Config) -> str:
    # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and on path /.
    return "__Host-mintrack_session" if _is_https(config) else "mintrack_session"


def _set_cookie(response: fastapi.Response, name: str, value: str, *, httponly: bool) -> None:
    """A first-party cookie that lasts as long as an idle session."""
    response.set_cookie(
        name,
        value,
        max_age=int(SESSION_IDLE_TIMEOUT.total_seconds()),
        path="/",
        secure=_is_https(get_config()),
        httponly=httponly,
        samesite="strict",
    )


def set_xsrf_cookie(response: fastapi.Response, xsrf_token: str | None = None) -> None:
    """The XSRF cookie, readable by the app, which echoes it in a header on unsafe requests."""
    _set_cookie(response, XSRF_COOKIE, xsrf_token or secrets.token_urlsafe(32), httponly=False)


def set_session_cookies(response: fastapi.Response, token: str, xsrf_token: str | None = None) -> None:
    _set_cookie(response, session_cookie_name(get_config()), token, httponly=True)
    set_xsrf_cookie(response, xsrf_token)


def clear_session_cookie(response: fastapi.Response) -> None:
    config = get_config()
    response.delete_cookie(
        session_cookie_name(config), path="/", secure=_is_https(config), httponly=True, samesite="strict"
    )


def _unauthenticated() -> fastapi.HTTPException:
    return fastapi.HTTPException(fastapi.status.HTTP_401_UNAUTHORIZED, "Not authenticated")


@dataclasses.dataclass(frozen=True)
class CurrentSession:
    user: User
    session_id: uuid.UUID


async def get_current_session(
    request: fastapi.Request, response: fastapi.Response, db: DbSessionDepType
) -> CurrentSession:
    token = request.cookies.get(session_cookie_name(get_config()))
    if not token:
        raise _unauthenticated()
    found = await AccountManager(db).get_session(token, now=utc_now())
    if found is None:
        raise _unauthenticated()
    user_session, user = found
    if AccountManager.touch_session(user_session, now=utc_now()):
        await db.commit()
        set_session_cookies(response, token, request.cookies.get(XSRF_COOKIE))
    return CurrentSession(user=user, session_id=user_session.id)


CurrentSessionDepType = typing.Annotated[CurrentSession, fastapi.Depends(get_current_session)]


async def get_current_user(current: CurrentSessionDepType) -> User:
    return current.user


CurrentUserDepType = typing.Annotated[User, fastapi.Depends(get_current_user)]


async def get_admin_user(user: CurrentUserDepType) -> User:
    if not user.is_admin:
        raise fastapi.HTTPException(fastapi.status.HTTP_403_FORBIDDEN, "Admins only")
    return user


async def check_xsrf(request: fastapi.Request) -> None:
    """Unsafe requests must echo the XSRF cookie in a header, which only a page of this origin can read."""
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(XSRF_COOKIE, "")
    header = request.headers.get(XSRF_HEADER, "")
    if not cookie or not secrets.compare_digest(cookie.encode(), header.encode()):
        raise fastapi.HTTPException(fastapi.status.HTTP_403_FORBIDDEN, "Missing or invalid XSRF token")
