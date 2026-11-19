import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.push.managers import PushManager
from mintrack.core.push.webpush import VapidKey
from mintrack.db.models import Media, MediaType, TrackingStatus, User
from tests.core.upcoming.factories import follow
from tests.push_service import Device, FakePushService

NOW = dt.datetime(2026, 11, 18, 8, 0, tzinfo=dt.UTC)
TODAY = NOW.date()


class World:
    """Users with movies on watch later, some released digitally."""

    def __init__(self, session: AsyncSession, push_service: FakePushService, key: VapidKey) -> None:
        self.session = session
        self.push_service = push_service
        self.key = key

    async def user(self, device: Device | None = None, *, active: bool = True) -> User:
        user = User(username=f"user-{uuid.uuid4()}", is_active=active)
        self.session.add(user)
        await self.session.flush()
        if device is not None:
            async with self.push_service.client() as client:
                await PushManager(self.session, client, self.key).subscribe(user, device.subscription, NOW)
        return user

    async def movie(
        self, user: User, released: dt.date | None, status: TrackingStatus = TrackingStatus.WATCH_LATER
    ) -> Media:
        movie = Media(
            media_type=MediaType.MOVIE,
            tmdb_id=uuid.uuid4().int % 1_000_000_000,
            title="Dune",
            digital_release_date=released,
            refreshed_at=NOW,
        )
        self.session.add(movie)
        await self.session.flush()
        await follow(self.session, user, movie, status)
        return movie

    async def run_job(self, now: dt.datetime = NOW) -> int:
        async with self.push_service.client() as client:
            return await PushManager(self.session, client, self.key).notify_digital_releases(now)


@pytest.fixture
def world(db_session: AsyncSession, push_service: FakePushService, vapid_key: VapidKey) -> World:
    return World(db_session, push_service, vapid_key)


async def test_a_movie_released_digitally_is_notified_once(
    world: World, push_service: FakePushService, device: Device
) -> None:
    user = await world.user(device)
    movie = await world.movie(user, TODAY)

    assert await world.run_job() == 1
    assert await world.run_job(NOW + dt.timedelta(days=1)) == 0

    [message] = push_service.received_by(device)
    assert message["notification"]["title"] == "Dune"
    assert message["notification"]["body"] == "Now available digitally"
    assert message["notification"]["data"]["onActionClick"]["default"]["url"] == f"/movies/{movie.tmdb_id}"


@pytest.mark.parametrize(("days_ago", "notified"), [(None, 0), (-1, 0), (0, 1), (7, 1), (8, 0)])
async def test_only_releases_within_the_last_week_are_notified(
    world: World, device: Device, days_ago: int | None, notified: int
) -> None:
    user = await world.user(device)
    await world.movie(user, None if days_ago is None else TODAY - dt.timedelta(days=days_ago))

    assert await world.run_job() == notified


@pytest.mark.parametrize(("status", "notified"), [(TrackingStatus.WATCH_LATER, 1), (TrackingStatus.WATCHED, 0)])
async def test_only_movies_on_watch_later_are_notified(
    world: World, device: Device, status: TrackingStatus, notified: int
) -> None:
    user = await world.user(device)
    await world.movie(user, TODAY, status)

    assert await world.run_job() == notified


async def test_users_without_a_device_or_disabled_are_not_notified(
    world: World, push_service: FakePushService, device: Device
) -> None:
    await world.movie(await world.user(), TODAY)
    await world.movie(await world.user(device, active=False), TODAY)

    assert await world.run_job() == 0
    assert push_service.requests == []
