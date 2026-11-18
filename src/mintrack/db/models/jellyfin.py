import datetime as dt
import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel
from mintrack.db.types import EncryptedText


class JellyfinSyncStatus(enum.StrEnum):
    OK = enum.auto()
    UNREACHABLE = enum.auto()
    UNAUTHORIZED = enum.auto()
    FAILED = enum.auto()


class JellyfinAccount(DatabaseModel):
    """A Jellyfin user linked to a MinTrack user, through an access token (the password is never stored)."""

    __tablename__ = "jellyfin_accounts"
    __table_args__ = (sa.UniqueConstraint("user_id", "server_id", "jellyfin_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    server_url: Mapped[str]
    server_id: Mapped[str]
    jellyfin_user_id: Mapped[str]
    username: Mapped[str]
    token: Mapped[str | None] = mapped_column(EncryptedText(b"mintrack jellyfin token"), nullable=False)
    # Highest LastPlayedDate already imported: the next sync reads only items played since.
    synced_until: Mapped[dt.datetime | None]
    last_sync_at: Mapped[dt.datetime | None]
    last_success_at: Mapped[dt.datetime | None]
    last_sync_status: Mapped[JellyfinSyncStatus | None] = mapped_column(
        sa.Enum(
            JellyfinSyncStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    last_sync_imported: Mapped[int] = mapped_column(default=0)
    last_sync_skipped: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
