import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel


class PushSubscription(DatabaseModel):
    """A browser's Web Push subscription: one per device, owned by the user signed in there."""

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The session that registered the device: signing out there, or its expiry, removes it.
    session_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("sessions.id", ondelete="SET NULL"), index=True)
    endpoint: Mapped[str] = mapped_column(unique=True)
    p256dh: Mapped[str]
    auth: Mapped[str]
    created_at: Mapped[dt.datetime]


class EpisodeNotification(DatabaseModel):
    """An episode a user was notified about, so each one is sent once."""

    __tablename__ = "episode_notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
