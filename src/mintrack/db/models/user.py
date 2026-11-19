import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel


class User(DatabaseModel):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    username: Mapped[str]
    # Null until the user sets a password through their link.
    password_hash: Mapped[str | None]
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    timezone: Mapped[str] = mapped_column(server_default="UTC")
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
    # The one live invitation or reset link: a new link replaces it, using it or disabling the user clears it.
    link_token_hash: Mapped[bytes | None] = mapped_column(sa.LargeBinary, unique=True)
    link_expires_at: Mapped[dt.datetime | None]
    # The last use of one of the user's sessions, as last written to it; it stays once the sessions are gone.
    last_seen_at: Mapped[dt.datetime | None]


sa.Index("unique_users_lower_username", sa.func.lower(User.username), unique=True)


class UserSession(DatabaseModel):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(User.id, ondelete="CASCADE"), index=True)
    token_hash: Mapped[bytes] = mapped_column(sa.LargeBinary, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
    last_used_at: Mapped[dt.datetime]
    # The browser's User-Agent at sign-in, cut to a bounded length, to name the device in the list of sessions.
    user_agent: Mapped[str | None]


class LoginFailure(DatabaseModel):
    __tablename__ = "login_failures"
    __table_args__ = (sa.Index(None, "address", "failed_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    username: Mapped[str]
    # The client's address; an IPv6 one as its /64 network, which one client usually holds whole.
    address: Mapped[str]
    failed_at: Mapped[dt.datetime]
