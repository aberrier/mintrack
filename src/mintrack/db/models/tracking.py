import datetime as dt
import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel

from .media import text_enum


class TrackingStatus(enum.StrEnum):
    """Shows use the first five, movies watch later and watched."""

    WATCH_LATER = enum.auto()
    WATCHING = enum.auto()
    UP_TO_DATE = enum.auto()
    FINISHED = enum.auto()
    STOPPED = enum.auto()
    WATCHED = enum.auto()


class UserMedia(DatabaseModel):
    """A movie or show in a user's library."""

    __tablename__ = "user_media"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    media_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("media.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    status: Mapped[TrackingStatus] = mapped_column(text_enum(TrackingStatus))
    added_at: Mapped[dt.datetime]
    updated_at: Mapped[dt.datetime]


class WatchedEpisode(DatabaseModel):
    __tablename__ = "watched_episodes"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    watched_at: Mapped[dt.datetime]


class WatchedMovie(DatabaseModel):
    __tablename__ = "watched_movies"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    media_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    watched_at: Mapped[dt.datetime]
