import asyncio
import datetime as dt
import enum
import functools
import importlib.resources
import ipaddress
import re
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import get_config
from mintrack.db.models import LoginFailure, PushSubscription, User, UserSession

from .devices import USER_AGENT_MAX_LENGTH
from .passwords import hash_password, needs_rehash, verify_password
from .tokens import hash_token, new_token

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{1,150}$"
SESSION_IDLE_TIMEOUT = dt.timedelta(days=14)
# last_used_at is written at most this often, which is also when the cookies' Max-Age is renewed.
SESSION_TOUCH_INTERVAL = dt.timedelta(hours=1)
INVITATION_LIFETIME = dt.timedelta(days=7)
RESET_LIFETIME = dt.timedelta(hours=24)
LOGIN_FAILURE_WINDOW = dt.timedelta(minutes=5)
# Per client address, whatever the usernames tried.
LOGIN_FAILURE_LIMIT = 5
_PG_TIMEZONE_NAMES = sa.table("pg_timezone_names", sa.column("name"))


class InvalidCredentialsError(Exception):
    pass


class LoginRateLimitedError(Exception):
    pass


class InvalidUsernameError(Exception):
    pass


class UsernameTakenError(Exception):
    pass


class LastAdminError(Exception):
    pass


class UserDisabledError(Exception):
    pass


class SetupClosedError(Exception):
    pass


class UserStatus(enum.StrEnum):
    INVITED = enum.auto()
    INVITATION_EXPIRED = enum.auto()
    ACTIVE = enum.auto()
    DISABLED = enum.auto()


def user_status(user: User, now: dt.datetime) -> UserStatus:
    if not user.is_active:
        return UserStatus.DISABLED
    if user.password_hash is not None:
        return UserStatus.ACTIVE
    if user.link_expires_at is not None and user.link_expires_at > now:
        return UserStatus.INVITED
    return UserStatus.INVITATION_EXPIRED


@functools.cache
def available_timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


@functools.cache
def _timezone_links() -> dict[str, str]:
    """Each legacy name of the tz database (Asia/Calcutta, US/Eastern...) and the zone it stands for."""
    source = importlib.resources.files("tzdata.zoneinfo").joinpath("tzdata.zi").read_text(encoding="utf-8")
    return {name: target for _, target, name in (line.split() for line in source.splitlines() if line[:2] == "L ")}


def canonical_timezone(name: str) -> str:
    """The zone's current name: browsers still report legacy names, which some PostgreSQL builds do not know."""
    links = _timezone_links()
    seen = {name}
    while (name := links.get(name, name)) not in seen:
        seen.add(name)
    return name


@functools.cache
def timezone_choices() -> dict[str, list[str]]:
    """Each zone to choose from by its current name, with its legacy names: UTC (rather than Etc/UTC) first, then
    the others sorted."""
    preferred = {"Etc/UTC": "UTC"}
    links = _timezone_links()
    choices: dict[str, list[str]] = {"UTC": []}
    for zone in sorted(available_timezones()):
        if zone not in links:
            choices.setdefault(preferred.get(zone, zone), [])
    for name in sorted(links):
        target = canonical_timezone(name)
        target = preferred.get(target, target)
        if target in choices and name != target:
            choices[target].append(name)
    return choices


async def database_timezone(session: AsyncSession, name: str) -> str | None:
    """`name`, or else its current name, as PostgreSQL knows it; None when PostgreSQL knows neither."""
    for candidate in dict.fromkeys((name, canonical_timezone(name))):
        if await session.scalar(sa.select(sa.exists().where(_PG_TIMEZONE_NAMES.c.name == candidate))):
            return candidate
    return None


def client_network(address: str) -> str:
    """The address login failures are counted for: an IPv6 address's /64, which one client usually holds whole."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


def is_valid_username(username: str) -> bool:
    return re.fullmatch(USERNAME_PATTERN, username) is not None


def _live_link(token: str, now: dt.datetime) -> tuple[sa.ColumnElement[bool], ...]:
    return User.link_token_hash == hash_token(token), User.link_expires_at > now, User.is_active.is_(True)


class AccountManager:
    """Accounts, sessions and links. Methods flush but never commit: the caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def login(
        self, username: str, password: str, *, address: str, now: dt.datetime, user_agent: str | None = None
    ) -> tuple[User, str]:
        """Return the user and a new session token, or raise the same error for every kind of failure."""
        key, address = username.lower(), client_network(address)
        await self._check_failure_limit(address, now)

        user = await self.session.scalar(sa.select(User).where(sa.func.lower(User.username) == key))
        password_hash = user.password_hash if user is not None and user.is_active else None
        verified = await asyncio.to_thread(verify_password, password_hash, password)
        if not verified or user is None or password_hash is None:
            await self._record_failure(key, address, now)
            raise InvalidCredentialsError

        await self.session.execute(
            sa.delete(LoginFailure).where(LoginFailure.username == key, LoginFailure.address == address)
        )
        if needs_rehash(password_hash):
            user.password_hash = await asyncio.to_thread(hash_password, password)
        return user, await self.create_session(user, now=now, user_agent=user_agent)

    async def _check_failure_limit(self, address: str, now: dt.datetime) -> None:
        # Attempts from one address wait for each other, so parallel requests can't all pass the count.
        await self.session.execute(sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext(f"login|{address}"))))
        failures = await self.session.scalar(
            sa.select(sa.func.count()).where(
                LoginFailure.address == address, LoginFailure.failed_at > now - LOGIN_FAILURE_WINDOW
            )
        )
        if (failures or 0) >= LOGIN_FAILURE_LIMIT:
            raise LoginRateLimitedError

    async def _record_failure(self, key: str, address: str, now: dt.datetime) -> None:
        await self.session.execute(sa.delete(LoginFailure).where(LoginFailure.failed_at <= now - LOGIN_FAILURE_WINDOW))
        self.session.add(LoginFailure(username=key, address=address, failed_at=now))
        await self.session.flush()

    async def setup_is_open(self) -> bool:
        """The first admin can be created from the browser while the setting allows it and no user exists at all."""
        return get_config().accounts.setup and not await self.session.scalar(sa.select(sa.exists(sa.select(User.id))))

    async def create_first_admin(
        self, username: str, password: str, *, address: str, now: dt.datetime, timezone: str | None = None
    ) -> User:
        """Create the first user, an active admin with this password; once only, limited like login.

        The caller checks the username against USERNAME_PATTERN. A time zone PostgreSQL does not know is ignored.
        """
        address = client_network(address)
        # Concurrent requests wait for each other, so only the first one finds no user.
        await self.session.execute(sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext("setup"))))
        await self._check_failure_limit(address, now)
        if not await self.setup_is_open():
            await self._record_failure(username.lower(), address, now)
            raise SetupClosedError
        user = User(
            username=username,
            password_hash=await asyncio.to_thread(hash_password, password),
            is_admin=True,
            is_active=True,
        )
        if timezone is not None and (known := await database_timezone(self.session, timezone)) is not None:
            user.timezone = known
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_session(self, user: User, *, now: dt.datetime, user_agent: str | None = None) -> str:
        token, token_hash = new_token()
        self.session.add(
            UserSession(
                user_id=user.id,
                token_hash=token_hash,
                last_used_at=now,
                user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
            )
        )
        user.last_seen_at = now
        await self.session.flush()
        return token

    async def list_sessions(self, user_id: uuid.UUID, *, now: dt.datetime) -> list[UserSession]:
        """The user's sessions still valid, the most recently used first."""
        sessions = await self.session.scalars(
            sa.select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.last_used_at > now - SESSION_IDLE_TIMEOUT)
            .order_by(UserSession.last_used_at.desc(), UserSession.id.desc())
        )
        return list(sessions)

    async def delete_user_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        """Sign out one of the user's sessions; False when the user has no such session."""
        owned = await self.session.scalar(
            sa.select(UserSession.id).where(UserSession.id == session_id, UserSession.user_id == user_id)
        )
        if owned is None:
            return False
        await self.delete_session(session_id)
        return True

    async def get_session(self, token: str, *, now: dt.datetime) -> tuple[UserSession, User] | None:
        """The session and its user, unless the session went unused too long or the user is disabled."""
        row = (
            await self.session.execute(
                sa.select(UserSession, User)
                .join(User)
                .where(
                    UserSession.token_hash == hash_token(token),
                    UserSession.last_used_at > now - SESSION_IDLE_TIMEOUT,
                    User.is_active,
                )
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    @staticmethod
    def touch_session(user_session: UserSession, user: User, *, now: dt.datetime) -> bool:
        """Record the use of a session by its user, at most once per interval; True when it was recorded."""
        if now - user_session.last_used_at < SESSION_TOUCH_INTERVAL:
            return False
        user_session.last_used_at = user.last_seen_at = now
        return True

    async def delete_session(self, session_id: uuid.UUID) -> None:
        """Sign out: the session and the device it registered for notifications."""
        await self.session.execute(sa.delete(PushSubscription).where(PushSubscription.session_id == session_id))
        await self.session.execute(sa.delete(UserSession).where(UserSession.id == session_id))

    async def delete_sessions(self, user_id: uuid.UUID, *, keep: uuid.UUID | None = None) -> None:
        """Sign out everywhere but `keep`, devices registered for notifications included; API tokens stay."""
        devices = sa.delete(PushSubscription).where(PushSubscription.user_id == user_id)
        sessions = sa.delete(UserSession).where(UserSession.user_id == user_id)
        if keep is not None:
            # Devices registered by `keep`, or by no session any more, stay: the latter may be this one.
            devices = devices.where(PushSubscription.session_id != keep)
            sessions = sessions.where(UserSession.id != keep)
        await self.session.execute(devices)
        await self.session.execute(sessions)

    async def delete_expired_sessions(self, now: dt.datetime) -> int:
        """Delete the sessions unused for longer than the idle timeout with the devices they registered for
        notifications, and the login failures out of the window."""
        expired = UserSession.last_used_at <= now - SESSION_IDLE_TIMEOUT
        await self.session.execute(
            sa.delete(PushSubscription).where(PushSubscription.session_id.in_(sa.select(UserSession.id).where(expired)))
        )
        deleted = await self.session.scalars(sa.delete(UserSession).where(expired).returning(UserSession.id))
        await self.session.execute(sa.delete(LoginFailure).where(LoginFailure.failed_at <= now - LOGIN_FAILURE_WINDOW))
        return len(deleted.all())

    @staticmethod
    def issue_link(user: User, *, now: dt.datetime) -> str:
        """A new invitation (no password yet) or reset link; it replaces the user's previous one."""
        if not user.is_active:
            raise UserDisabledError
        token, token_hash = new_token()
        user.link_token_hash = token_hash
        user.link_expires_at = now + (INVITATION_LIFETIME if user.password_hash is None else RESET_LIFETIME)
        return token

    async def find_link_user(self, token: str, *, now: dt.datetime) -> User | None:
        return await self.session.scalar(sa.select(User).where(*_live_link(token, now)))

    async def use_link(self, token: str, password: str, *, timezone: str | None, now: dt.datetime) -> User | None:
        """Set the password and consume the link in one statement, so a link works once; revoke the sessions."""
        values: dict[str, object] = {
            "password_hash": await asyncio.to_thread(hash_password, password),
            "link_token_hash": None,
            "link_expires_at": None,
        }
        if timezone is not None:
            # The browser's time zone is only taken when the user had no password yet.
            values["timezone"] = sa.case((User.password_hash.is_(None), timezone), else_=User.timezone)
        user = await self.session.scalar(
            sa.update(User).where(*_live_link(token, now)).values(values).returning(User),
            execution_options={"synchronize_session": False, "populate_existing": True},
        )
        if user is not None:
            await self.delete_sessions(user.id)
        return user

    async def change_password(
        self, user: User, current_password: str, new_password: str, *, keep_session: uuid.UUID
    ) -> None:
        if not await asyncio.to_thread(verify_password, user.password_hash, current_password):
            raise InvalidCredentialsError
        user.password_hash = await asyncio.to_thread(hash_password, new_password)
        await self.delete_sessions(user.id, keep=keep_session)

    async def create_user(self, username: str, *, is_admin: bool, now: dt.datetime) -> tuple[User, str]:
        """Create a user without a password and return it with its invitation link token."""
        if not is_valid_username(username):
            raise InvalidUsernameError
        user = User(username=username, is_admin=is_admin, is_active=True)
        token = self.issue_link(user, now=now)
        try:
            async with self.session.begin_nested():
                self.session.add(user)
        except IntegrityError:
            raise UsernameTakenError from None
        return user, token

    async def get_user(self, username: str) -> User | None:
        return await self.session.scalar(sa.select(User).where(sa.func.lower(User.username) == username.lower()))

    async def list_users(self) -> list[User]:
        return list(await self.session.scalars(sa.select(User).order_by(sa.func.lower(User.username))))

    async def set_active(self, user: User, *, active: bool) -> None:
        """Enable or disable a user; disabling revokes their sessions and link and keeps one active admin."""
        if active:
            user.is_active = True
            return
        if user.is_admin:
            # Locking every active admin serialises concurrent disables, so they can't remove the last one together.
            active_admins = (
                await self.session.scalars(sa.select(User.id).where(User.is_admin, User.is_active).with_for_update())
            ).all()
            if user.id in active_admins and len(active_admins) == 1:
                raise LastAdminError
        user.is_active = False
        user.link_token_hash = None
        user.link_expires_at = None
        await self.delete_sessions(user.id)
