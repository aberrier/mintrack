import datetime as dt
import enum
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel
from mintrack.db.types import EncryptedText


class JellyfinSyncStatus(enum.StrEnum):
    OK = enum.auto()
    UNREACHABLE = enum.auto()
    UNAUTHORIZED = enum.auto()
    FAILED = enum.auto()


class JellyfinUnmatchedReason(enum.StrEnum):
    # Neither a movie nor an episode.
    UNSUPPORTED = enum.auto()
    # An episode without a season or episode number.
    NO_NUMBERS = enum.auto()
    # No provider id TMDB knows, and no title TMDB answers alone.
    NOT_FOUND = enum.auto()
    # TMDB knows the show, not this episode.
    EPISODE_NOT_FOUND = enum.auto()


class JellyfinUnmatchedItem(typing.TypedDict):
    """A played item no watch was found for, as Jellyfin describes it."""

    name: str
    type: str
    year: int | None
    provider_ids: dict[str, str]
    series_name: str | None
    series_year: int | None
    series_provider_ids: dict[str, str] | None
    season: int | None
    episode: int | None
    reason: JellyfinUnmatchedReason


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
    # The first of them, at the last full sync, one entry per series not found.
    last_sync_unmatched: Mapped[list[JellyfinUnmatchedItem]] = mapped_column(
        JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
