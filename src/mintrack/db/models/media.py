import datetime as dt
import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel


class MediaType(enum.StrEnum):
    MOVIE = enum.auto()
    TV = enum.auto()


def text_enum[E: enum.StrEnum](enum_class: type[E]) -> sa.Enum:
    """Stored as its values in a text column with a check constraint, so adding a value is a plain migration."""
    return sa.Enum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        length=None,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class Media(DatabaseModel):
    """A movie or a TV show (anime included), cached from TMDB."""

    __tablename__ = "media"
    __table_args__ = (sa.UniqueConstraint("media_type", "tmdb_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    media_type: Mapped[MediaType] = mapped_column(text_enum(MediaType))
    tmdb_id: Mapped[int]
    title: Mapped[str]
    overview: Mapped[str] = mapped_column(default="")
    poster_path: Mapped[str | None]
    backdrop_path: Mapped[str | None]
    # The show's first network; None for movies.
    network: Mapped[str | None]
    # The movie's length in minutes; None for shows.
    runtime: Mapped[int | None]
    # The movie's release date or the show's first air date.
    release_date: Mapped[dt.date | None]
    # TMDB's status: "Returning Series", "Ended", "Released"...
    tmdb_status: Mapped[str | None]
    tvdb_id: Mapped[int | None]
    tvmaze_id: Mapped[int | None]
    refreshed_at: Mapped[dt.datetime]


class Season(DatabaseModel):
    __tablename__ = "seasons"
    __table_args__ = (sa.UniqueConstraint("media_id", "season_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    media_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("media.id", ondelete="CASCADE"))
    season_number: Mapped[int]
    title: Mapped[str]


class Episode(DatabaseModel):
    __tablename__ = "episodes"
    __table_args__ = (sa.UniqueConstraint("media_id", "season_number", "episode_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    media_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("media.id", ondelete="CASCADE"))
    # Season 0 holds the specials.
    season_number: Mapped[int]
    episode_number: Mapped[int]
    title: Mapped[str]
    air_date: Mapped[dt.date | None]
    # Exact air time in UTC when known; TMDB only gives the date.
    airstamp: Mapped[dt.datetime | None]
