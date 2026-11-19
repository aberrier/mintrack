import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel

MIN_STARS = 1
MAX_STARS = 5
MAX_REVIEW_LENGTH = 500


def rating_checks() -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    return (
        sa.CheckConstraint(f"stars BETWEEN {MIN_STARS} AND {MAX_STARS}", name="stars"),
        sa.CheckConstraint(f"char_length(review) <= {MAX_REVIEW_LENGTH}", name="review_length"),
    )


class MediaRating(DatabaseModel):
    """A user's own rating of a show or a movie, seen only by them."""

    __tablename__ = "media_ratings"
    __table_args__ = rating_checks()

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    media_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("media.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    stars: Mapped[int] = mapped_column(sa.SmallInteger)
    # "" without a review.
    review: Mapped[str]
    updated_at: Mapped[dt.datetime]


class EpisodeRating(DatabaseModel):
    """A user's own rating of an episode, seen only by them."""

    __tablename__ = "episode_ratings"
    __table_args__ = rating_checks()

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    stars: Mapped[int] = mapped_column(sa.SmallInteger)
    review: Mapped[str]
    updated_at: Mapped[dt.datetime]
