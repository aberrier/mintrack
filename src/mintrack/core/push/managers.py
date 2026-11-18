import datetime as dt
import json
import uuid

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import episode_code
from mintrack.core.upcoming.managers import IN_PROGRESS_STATUSES
from mintrack.db.models import Episode, EpisodeNotification, Media, PushSubscription, User, UserMedia
from mintrack.observability.logging import logger

from .webpush import SendResult, Subscription, VapidKey, send

# An episode is notified when it aired during this window before the job runs (every 10 minutes).
NOTIFICATION_WINDOW = dt.timedelta(minutes=30)
# When only the air date is known, the episode counts as aired at this hour in the user's time zone.
FALLBACK_AIR_TIME = dt.timedelta(hours=9)
# Each device costs a request per notification: a user cannot register an unbounded number of them.
MAX_DEVICES = 20
ICON = "/icons/icon-192.png"


def notification(title: str, body: str, tag: str, url: str | None = None) -> bytes:
    """A message in the format Angular's service worker shows; a tap opens `url` in the app's window, or without
    `url` focuses the app as it is."""
    action = (
        {"operation": "focusLastFocusedOrOpen", "url": "/"}
        if url is None
        else {"operation": "navigateLastFocusedOrOpen", "url": url}
    )
    return json.dumps(
        {
            "notification": {
                "title": title,
                "body": body,
                "icon": ICON,
                "tag": tag,
                "data": {"onActionClick": {"default": action}},
            }
        }
    ).encode()


def episodes_notification(show: Media, episodes: list[Episode]) -> bytes:
    """One message per show: a season released at once is one notification, not one per episode."""
    if len(episodes) == 1:
        [episode] = episodes
        body = episode_code(episode.season_number, episode.episode_number)
        if episode.title:
            body += f" · {episode.title}"
    else:
        body = f"{len(episodes)} new episodes"
    return notification(show.title, body, tag=str(show.id), url=f"/shows/{show.tmdb_id}")


TEST_NOTIFICATION = notification("MinTrack", "Notifications work on this device.", tag="test")


class PushManager:
    def __init__(self, session: AsyncSession, client: httpx.AsyncClient, key: VapidKey) -> None:
        self.session = session
        self.client = client
        self.key = key

    async def subscribe(
        self, user: User, subscription: Subscription, now: dt.datetime, *, session_id: uuid.UUID | None = None
    ) -> None:
        """Register this device for the user, signed in with `session_id`; a device already registered by someone
        else moves to this user.

        Beyond MAX_DEVICES, the user's devices registered longest ago are dropped.
        """
        values = {
            "user_id": user.id,
            "session_id": session_id,
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
            "created_at": now,
        }
        await self.session.execute(
            insert(PushSubscription)
            .values(endpoint=subscription.endpoint, **values)
            .on_conflict_do_update(index_elements=[PushSubscription.endpoint], set_=values)
        )
        newest = (
            sa.select(PushSubscription.id)
            .where(PushSubscription.user_id == user.id)
            .order_by(PushSubscription.created_at.desc())
            .limit(MAX_DEVICES)
        )
        await self.session.execute(
            sa.delete(PushSubscription).where(
                PushSubscription.user_id == user.id, PushSubscription.id.not_in(newest.scalar_subquery())
            )
        )
        await self.session.commit()

    async def unsubscribe(self, user: User, endpoint: str) -> None:
        await self.session.execute(
            sa.delete(PushSubscription).where(
                PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
            )
        )
        await self.session.commit()

    async def send_test(self, user: User, endpoint: str, now: dt.datetime) -> SendResult | None:
        """Send the test notification to one of the user's devices; None when it is not registered."""
        subscription = await self.session.scalar(
            sa.select(PushSubscription).where(
                PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
            )
        )
        if subscription is None:
            return None
        result = await self._send(subscription, TEST_NOTIFICATION, now)
        await self.session.commit()
        return result

    async def notify_aired_episodes(self, now: dt.datetime) -> int:
        """Notify each user once about the episodes of followed shows aired within the window, one message per show.

        The pairs are recorded and committed before sending, so concurrent or repeated runs never send one twice.
        Returns the number of episodes notified.
        """
        users = await self.session.scalars(
            sa.select(User).where(User.is_active, sa.exists().where(PushSubscription.user_id == User.id))
        )
        claimed: list[tuple[uuid.UUID, uuid.UUID]] = []
        for user in users.all():
            try:
                # One user's failure (a time zone PostgreSQL does not know...) leaves the others' notifications.
                async with self.session.begin_nested():
                    claimed.extend(await self._claim(user, now))
            except DBAPIError:
                logger.exception("episode notifications failed for a user", user_id=str(user.id))
        await self.session.commit()
        if not claimed:
            return 0

        released: dict[tuple[uuid.UUID, Media], list[Episode]] = {}
        claimed_episodes = await self.session.execute(
            sa.select(EpisodeNotification.user_id, Episode, Media)
            .join(Episode, Episode.id == EpisodeNotification.episode_id)
            .join(Media, Media.id == Episode.media_id)
            .where(sa.tuple_(EpisodeNotification.user_id, EpisodeNotification.episode_id).in_(claimed))
            .order_by(Episode.season_number, Episode.episode_number)
        )
        for user_id, episode, show in claimed_episodes:
            released.setdefault((user_id, show), []).append(episode)
        devices: dict[uuid.UUID, list[PushSubscription]] = {}
        for subscription in await self.session.scalars(
            sa.select(PushSubscription).where(PushSubscription.user_id.in_({user_id for user_id, _ in claimed}))
        ):
            devices.setdefault(subscription.user_id, []).append(subscription)

        for (user_id, show), episodes in released.items():
            for subscription in list(devices.get(user_id, [])):
                if await self._send(subscription, episodes_notification(show, episodes), now) is SendResult.GONE:
                    devices[user_id].remove(subscription)
        await self.session.commit()
        return len(claimed)

    async def _claim(self, user: User, now: dt.datetime) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Record the user's episodes of followed shows aired within the window and not notified yet."""
        aired_at = sa.func.coalesce(
            Episode.airstamp,
            sa.func.timezone(user.timezone, sa.cast(Episode.air_date, sa.DateTime) + FALLBACK_AIR_TIME),
        )
        due = (
            sa.select(sa.literal(user.id, sa.Uuid), Episode.id)
            .join(UserMedia, UserMedia.media_id == Episode.media_id)
            .where(
                UserMedia.user_id == user.id,
                UserMedia.status.in_(IN_PROGRESS_STATUSES),
                # Narrows the scan to a few days of episodes before comparing the computed air time.
                Episode.air_date.between((now - dt.timedelta(days=2)).date(), (now + dt.timedelta(days=1)).date()),
                aired_at > now - NOTIFICATION_WINDOW,
                aired_at <= now,
            )
        )
        rows = await self.session.execute(
            insert(EpisodeNotification)
            .from_select(["user_id", "episode_id"], due)
            .on_conflict_do_nothing()
            .returning(EpisodeNotification.user_id, EpisodeNotification.episode_id)
        )
        return [(user_id, episode_id) for user_id, episode_id in rows]

    async def _send(self, subscription: PushSubscription, payload: bytes, now: dt.datetime) -> SendResult:
        target = Subscription(endpoint=subscription.endpoint, p256dh=subscription.p256dh, auth=subscription.auth)
        result = await send(self.client, self.key, target, payload, now)
        if result is SendResult.GONE:
            await self.session.delete(subscription)
        return result
