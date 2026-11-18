import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.push.managers import MAX_DEVICES, PushManager
from mintrack.core.push.webpush import SendResult, VapidKey
from mintrack.db.models import Episode, EpisodeNotification, Media, PushSubscription, TrackingStatus, User
from tests.core.upcoming.factories import add_show, follow
from tests.push_service import Device, FakePushService

# 20:00 UTC is 21:00 in Paris: an episode dated today in Paris "aired" at 09:00 there, 12 hours ago.
NOW = dt.datetime(2026, 11, 18, 20, 0, tzinfo=dt.UTC)


class World:
    """A user following shows on one device, with episodes airing around NOW."""

    def __init__(self, session: AsyncSession, push_service: FakePushService, key: VapidKey) -> None:
        self.session = session
        self.push_service = push_service
        self.key = key

    async def user(self, timezone: str = "UTC", *, active: bool = True) -> User:
        user = User(username=f"user-{timezone}-{active}", timezone=timezone, is_active=active)
        self.session.add(user)
        await self.session.flush()
        return user

    async def show(
        self, user: User, status: TrackingStatus = TrackingStatus.WATCHING, title: str = "Severance"
    ) -> Media:
        show, _ = await add_show(self.session, {}, title=title)
        await follow(self.session, user, show, status)
        return show

    async def episode(
        self, show: Media, number: int, *, airstamp: dt.datetime | None = None, air_date: dt.date | None = None
    ) -> Episode:
        episode = Episode(
            media_id=show.id,
            season_number=2,
            episode_number=number,
            title=f"Episode {number}",
            airstamp=airstamp,
            air_date=air_date or (airstamp.date() if airstamp else None),
        )
        self.session.add(episode)
        await self.session.flush()
        return episode

    async def subscribe(self, user: User, device: Device, now: dt.datetime = NOW) -> None:
        async with self.push_service.client() as client:
            await PushManager(self.session, client, self.key).subscribe(user, device.subscription, now)

    async def run_job(self, now: dt.datetime = NOW) -> int:
        async with self.push_service.client() as client:
            return await PushManager(self.session, client, self.key).notify_aired_episodes(now)


@pytest.fixture
def world(db_session: AsyncSession, push_service: FakePushService, vapid_key: VapidKey) -> World:
    return World(db_session, push_service, vapid_key)


def bodies(messages: list[dict]) -> list[str]:
    return sorted(message["notification"]["body"] for message in messages)


async def test_an_episode_is_notified_once_when_it_airs(
    world: World, push_service: FakePushService, device: Device
) -> None:
    user = await world.user()
    show = await world.show(user)
    await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=5))
    await world.subscribe(user, device)

    assert await world.run_job() == 1
    assert await world.run_job(NOW + dt.timedelta(minutes=10)) == 0

    [message] = push_service.received_by(device)
    assert message["notification"]["title"] == "Severance"
    assert message["notification"]["body"] == "S02E01 · Episode 1"
    assert message["notification"]["data"]["onActionClick"]["default"] == {
        "operation": "navigateLastFocusedOrOpen",
        "url": f"/shows/{show.tmdb_id}",
    }


async def test_a_user_whose_time_zone_postgresql_does_not_know_leaves_the_others_notified(
    world: World, push_service: FakePushService, device: Device
) -> None:
    # Stored before time zones were checked against PostgreSQL.
    stranded = await world.user("Not/A_Zone")
    stranded_device = Device("https://fcm.googleapis.com/fcm/send/stranded")
    await world.episode(await world.show(stranded, title="Andor"), 1, air_date=NOW.date())
    await world.subscribe(stranded, stranded_device)
    user = await world.user()
    await world.episode(await world.show(user), 1, airstamp=NOW - dt.timedelta(minutes=5))
    await world.subscribe(user, device)

    assert await world.run_job() == 1

    assert len(push_service.received_by(device)) == 1
    assert push_service.received_by(stranded_device) == []


async def test_only_episodes_that_aired_within_the_window_are_notified(
    world: World, db_session: AsyncSession, device: Device
) -> None:
    user = await world.user()
    show = await world.show(user)
    await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=29))
    await world.episode(show, 2, airstamp=NOW - dt.timedelta(minutes=31))
    await world.episode(show, 3, airstamp=NOW + dt.timedelta(minutes=1))
    await world.episode(show, 4, airstamp=NOW)
    await world.subscribe(user, device)

    assert await world.run_job() == 2

    notified = await db_session.scalars(
        sa.select(Episode.episode_number).join(EpisodeNotification).order_by(Episode.episode_number)
    )
    assert list(notified) == [1, 4]


async def test_episodes_released_together_make_one_notification_per_show(
    world: World, push_service: FakePushService, device: Device
) -> None:
    user = await world.user()
    show = await world.show(user)
    for number in (1, 2, 3):
        await world.episode(show, number, airstamp=NOW - dt.timedelta(minutes=5))
    other = await world.show(user, title="Andor")
    await world.episode(other, 1, airstamp=NOW - dt.timedelta(minutes=5))
    await world.subscribe(user, device)

    assert await world.run_job() == 4

    messages = {
        message["notification"]["title"]: message["notification"] for message in push_service.received_by(device)
    }
    assert messages["Severance"]["body"] == "3 new episodes"
    assert messages["Severance"]["tag"] == str(show.id)
    assert messages["Andor"]["body"] == "S02E01 · Episode 1"


async def test_without_an_air_time_the_episode_airs_at_nine_in_the_user_time_zone(
    world: World, push_service: FakePushService, device: Device
) -> None:
    # 09:00 in Tokyo on 19 November is 00:00 UTC on 19 November.
    user = await world.user("Asia/Tokyo")
    show = await world.show(user)
    await world.episode(show, 1, air_date=dt.date(2026, 11, 19))
    await world.subscribe(user, device)

    assert await world.run_job(dt.datetime(2026, 11, 18, 23, 59, tzinfo=dt.UTC)) == 0
    assert await world.run_job(dt.datetime(2026, 11, 19, 0, 5, tzinfo=dt.UTC)) == 1

    assert bodies(push_service.received_by(device)) == ["S02E01 · Episode 1"]


@pytest.mark.parametrize(
    ("status", "notified"),
    [
        (TrackingStatus.WATCHING, 1),
        (TrackingStatus.UP_TO_DATE, 1),
        (TrackingStatus.NOT_STARTED, 1),
        (TrackingStatus.WATCH_LATER, 0),
        (TrackingStatus.FINISHED, 0),
        (TrackingStatus.STOPPED, 0),
    ],
)
async def test_only_followed_shows_are_notified(
    world: World, device: Device, status: TrackingStatus, notified: int
) -> None:
    user = await world.user()
    show = await world.show(user, status)
    await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=5))
    await world.subscribe(user, device)

    assert await world.run_job() == notified


async def test_disabled_users_are_not_notified(world: World, push_service: FakePushService, device: Device) -> None:
    user = await world.user(active=False)
    show = await world.show(user)
    await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=5))
    await world.subscribe(user, device)

    assert await world.run_job() == 0
    assert push_service.requests == []


async def test_every_device_of_the_user_is_notified_and_expired_ones_are_deleted(
    world: World, db_session: AsyncSession, push_service: FakePushService, device: Device
) -> None:
    user = await world.user()
    for title in ("Severance", "Andor"):
        show = await world.show(user, title=title)
        await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=5))
    expired = Device("https://web.push.apple.com/expired")
    await world.subscribe(user, device)
    await world.subscribe(user, expired)
    push_service.statuses[expired.endpoint] = 410

    assert await world.run_job() == 2

    titles = [message["notification"]["title"] for message in push_service.received_by(device)]
    assert sorted(titles) == ["Andor", "Severance"]
    # The expired device is tried once, then forgotten.
    assert [str(request.url) for request in push_service.requests].count(expired.endpoint) == 1
    endpoints = await db_session.scalars(sa.select(PushSubscription.endpoint))
    assert list(endpoints) == [device.endpoint]


async def test_users_without_a_device_are_skipped(world: World) -> None:
    user = await world.user()
    show = await world.show(user)
    await world.episode(show, 1, airstamp=NOW - dt.timedelta(minutes=5))

    assert await world.run_job() == 0


async def test_a_device_moves_to_the_user_who_subscribes_it_last(
    world: World, db_session: AsyncSession, device: Device
) -> None:
    first = await world.user("UTC")
    second = await world.user("Europe/Paris")
    await world.subscribe(first, device)
    await world.subscribe(second, device)

    owners = await db_session.scalars(sa.select(PushSubscription.user_id))
    assert list(owners) == [second.id]


async def test_the_test_notification_reaches_only_the_user_device(
    world: World, push_service: FakePushService, vapid_key: VapidKey, db_session: AsyncSession, device: Device
) -> None:
    owner = await world.user("UTC")
    other = await world.user("Europe/Paris")
    await world.subscribe(owner, device)

    async with push_service.client() as client:
        manager = PushManager(db_session, client, vapid_key)
        assert await manager.send_test(other, device.endpoint, NOW) is None
        assert await manager.send_test(owner, device.endpoint, NOW) is SendResult.SENT

    [message] = push_service.received_by(device)
    assert message["notification"]["body"] == "Notifications work on this device."


async def test_a_user_keeps_only_the_most_recently_registered_devices(world: World, db_session: AsyncSession) -> None:
    user = await world.user()
    devices = [Device(f"https://fcm.googleapis.com/fcm/send/device-{number}") for number in range(MAX_DEVICES + 1)]
    for minutes, device in enumerate(devices):
        await world.subscribe(user, device, NOW + dt.timedelta(minutes=minutes))

    endpoints = set(await db_session.scalars(sa.select(PushSubscription.endpoint)))
    assert endpoints == {device.endpoint for device in devices[1:]}
