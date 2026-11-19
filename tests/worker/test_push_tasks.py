import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.push.managers import PushManager
from mintrack.core.push.webpush import VapidKey
from mintrack.db.models import Media, MediaType, TrackingStatus
from mintrack.worker import tasks
from tests.core.upcoming.factories import add_show, add_user, follow
from tests.push_service import Device, FakePushService

NOW = dt.datetime(2026, 11, 18, 20, 0, tzinfo=dt.UTC)


@pytest.fixture
async def subscribed(
    db_session: AsyncSession, push_service: FakePushService, vapid_key: VapidKey, device: Device
) -> Device:
    """A device of a user following a show whose episode aired five minutes before NOW."""
    user = await add_user(db_session)
    show, _ = await add_show(db_session, {(1, 1): NOW - dt.timedelta(minutes=5)}, title="Severance")
    await follow(db_session, user, show, TrackingStatus.WATCHING)
    async with push_service.client() as client:
        await PushManager(db_session, client, vapid_key).subscribe(user, device.subscription, NOW)
    return device


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_the_job_notifies_the_episodes_aired_before_its_scheduled_time(
    subscribed: Device, push_service: FakePushService, vapid_key: VapidKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_vapid_key", lambda: vapid_key)
    monkeypatch.setattr(tasks, "push_client", push_service.client)

    await tasks.notify_aired_episodes(timestamp=int(NOW.timestamp()))

    [message] = push_service.received_by(subscribed)
    assert message["notification"]["title"] == "Severance"


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_without_push_configured_the_job_sends_nothing(
    subscribed: Device, push_service: FakePushService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_vapid_key", lambda: None)
    monkeypatch.setattr(tasks, "push_client", push_service.client)

    await tasks.notify_aired_episodes(timestamp=int(NOW.timestamp()))
    await tasks.notify_digital_releases(timestamp=int(NOW.timestamp()))

    assert push_service.received_by(subscribed) == []


@pytest.mark.usefixtures("jobs_on_test_session")
async def test_the_daily_job_notifies_the_movies_released_digitally(
    db_session: AsyncSession,
    push_service: FakePushService,
    vapid_key: VapidKey,
    device: Device,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await add_user(db_session)
    movie = Media(
        media_type=MediaType.MOVIE,
        tmdb_id=1,
        title="Dune",
        digital_release_date=NOW.date(),
        refreshed_at=NOW,
    )
    db_session.add(movie)
    await db_session.flush()
    await follow(db_session, user, movie, TrackingStatus.WATCH_LATER)
    async with push_service.client() as client:
        await PushManager(db_session, client, vapid_key).subscribe(user, device.subscription, NOW)
    monkeypatch.setattr(tasks, "get_vapid_key", lambda: vapid_key)
    monkeypatch.setattr(tasks, "push_client", push_service.client)

    await tasks.notify_digital_releases(timestamp=int(NOW.timestamp()))

    [message] = push_service.received_by(device)
    assert message["notification"]["title"] == "Dune"
