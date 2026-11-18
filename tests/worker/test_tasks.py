import collections.abc
import contextlib
import datetime as dt
import logging
import types
import typing
import uuid

import procrastinate
import pytest
import pytest_asyncio
import sqlalchemy as sa
from procrastinate.jobs import Job

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import ShowTrackingChoice, TrackingManager
from mintrack.db.database import DatabaseManager
from mintrack.db.models import Episode, Media, MediaType, User
from mintrack.integrations.tmdb.client import TMDBClient
from mintrack.integrations.tvmaze.client import TvmazeClient
from mintrack.observability.config import LogLevel, ObservabilityConfig
from mintrack.observability.logging import configure_logging
from mintrack.worker import defer, tasks
from mintrack.worker.app import WORKER_DEFAULTS, get_worker_app
from tests.conftest import make_tmdb_client
from tests.fakes.tmdb import INVALID_KEY, FakeTMDB
from tests.fakes.tvmaze import FakeTvmaze, tvmaze_episode


@pytest_asyncio.fixture
async def committed_show(database: DatabaseManager, tmdb: TMDBClient) -> collections.abc.AsyncGenerator[Media]:
    """A show committed for real, as the worker reads it from its own connections; deleted afterwards."""
    title = f"Worker Show {uuid.uuid4()}"
    async with database.session() as session:
        tmdb_id = (await tmdb.search(title))[0].id
        media = await CatalogManager(session, tmdb).fetch(MediaType.TV, tmdb_id, dt.datetime.now(dt.UTC))
        await session.commit()
    yield media
    async with database.session() as session:
        await session.execute(sa.delete(Media).where(Media.id == media.id))
        await session.execute(
            sa.text("DELETE FROM procrastinate_jobs WHERE args->>'media_id' = :id"), {"id": str(media.id)}
        )
        await session.commit()


@pytest_asyncio.fixture
async def committed_user(database: DatabaseManager) -> collections.abc.AsyncGenerator[User]:
    async with database.session() as session:
        user = User(username=f"worker-{uuid.uuid4()}")
        session.add(user)
        await session.commit()
    yield user
    async with database.session() as session:
        await session.execute(sa.delete(User).where(User.id == user.id))
        await session.commit()


async def run_refresh(database: DatabaseManager, media: Media) -> str:
    """Defer a refresh, run the worker until the queue is empty, and return the job's status."""
    async with database.session() as session:
        await defer.defer_refresh(session, media.id)
        await session.commit()
    app = get_worker_app()
    async with app.open_async():
        await app.run_worker_async(wait=False, install_signal_handlers=False, delete_jobs="never")
    async with database.session() as session:
        return await session.scalar(
            sa.text("SELECT status FROM procrastinate_jobs WHERE args->>'media_id' = :id ORDER BY id DESC LIMIT 1"),
            {"id": str(media.id)},
        )


async def test_the_worker_refreshes_a_media_from_tmdb(
    database: DatabaseManager,
    committed_show: Media,
    fake_tmdb: FakeTMDB,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: tmdb)
    fake_tmdb.titles[committed_show.tmdb_id] = "Renamed on TMDB"

    status = await run_refresh(database, committed_show)

    async with database.session() as session:
        refreshed = await session.get_one(Media, committed_show.id)
    assert status == "succeeded"
    assert refreshed.title == "Renamed on TMDB"


async def test_a_failing_refresh_never_logs_the_tmdb_key(
    database: DatabaseManager,
    committed_show: Media,
    fake_tmdb: FakeTMDB,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: make_tmdb_client(fake_tmdb, api_key=INVALID_KEY))
    configure_logging(ObservabilityConfig(level=LogLevel.INFO))
    # dictConfig replaced the root handlers, pytest's included.
    logging.getLogger().addHandler(caplog.handler)

    status = await run_refresh(database, committed_show)

    assert status == "todo"
    assert "TMDB rejected the API key" in caplog.text
    assert INVALID_KEY not in caplog.text


async def test_the_hourly_run_defers_a_refresh_of_stale_tracked_media(
    database: DatabaseManager,
    committed_show: Media,
    committed_user: User,
    tmdb: TMDBClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: tmdb)
    async with database.session() as session:
        await TrackingManager(session).set_show_status(
            committed_user, committed_show, ShowTrackingChoice.WATCHING, dt.datetime.now(dt.UTC)
        )
        await session.execute(
            sa.update(Media)
            .where(Media.id == committed_show.id)
            .values(refreshed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=2))
        )
        await session.commit()

    await tasks.refresh_stale_media(timestamp=0)

    async with database.session() as session:
        queued = await session.scalar(
            sa.text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status = 'todo' AND task_name LIKE '%refresh_media' AND args->>'media_id' = :id"
            ),
            {"id": str(committed_show.id)},
        )
    assert queued == 1


def test_air_times_are_refreshed_daily() -> None:
    app = get_worker_app()

    task = app.tasks["mintrack:refresh_air_times"]
    assert [periodic.cron for periodic in app.periodic_registry.periodic_tasks.values() if periodic.task is task] == [
        "0 4 * * *"
    ]


def test_the_managers_defer_tasks_the_worker_runs() -> None:
    assert {f"{defer.NAMESPACE}:{name}" for name in defer.TaskName} <= set(get_worker_app().tasks)


@pytest.mark.parametrize("name", ["mintrack:refresh_media", "mintrack:refresh_show_air_times"])
def test_jobs_calling_outside_services_are_retried_twice_5_then_10_minutes_later(name: str) -> None:
    strategy = get_worker_app().tasks[name].retry_strategy
    assert strategy is not None

    def wait(attempts: int) -> object:
        job = Job(queue="default", lock=None, queueing_lock=None, task_name=name, attempts=attempts)
        decision = strategy.get_retry_decision(exception=RuntimeError(), job=job)
        return None if decision is None else decision.retry_at

    before = dt.datetime.now(dt.UTC)
    first, second, third = wait(1), wait(2), wait(3)
    assert isinstance(first, dt.datetime)
    assert isinstance(second, dt.datetime)
    assert dt.timedelta(minutes=5) <= first - before < dt.timedelta(minutes=6)
    assert dt.timedelta(minutes=10) <= second - before < dt.timedelta(minutes=11)
    assert third is None


def test_the_worker_runs_several_jobs_at_once() -> None:
    assert get_worker_app().worker_defaults["concurrency"] == WORKER_DEFAULTS["concurrency"] == 4


async def test_a_tracked_show_gets_its_exact_air_times(
    database: DatabaseManager, committed_show: Media, monkeypatch: pytest.MonkeyPatch
) -> None:
    airstamp = dt.datetime(2026, 11, 21, 2, tzinfo=dt.UTC)
    fake = FakeTvmaze(shows={committed_show.tvdb_id or 0: (169, [tvmaze_episode(1, 1, airstamp.isoformat())])})

    @contextlib.asynccontextmanager
    async def tvmaze_client() -> collections.abc.AsyncGenerator[TvmazeClient]:
        yield fake.client()

    monkeypatch.setattr(tasks, "tvmaze_client", tvmaze_client)

    await tasks.refresh_show_air_times_task(media_id=str(committed_show.id))

    async with database.session() as session:
        first = await session.scalar(
            sa.select(Episode.airstamp).where(
                Episode.media_id == committed_show.id, Episode.season_number == 1, Episode.episode_number == 1
            )
        )
    assert first == airstamp


async def test_the_jobs_of_a_worker_that_stopped_are_retried(database: DatabaseManager) -> None:
    async with database.engine.begin() as connection:
        worker_id = await connection.scalar(
            sa.text(
                "INSERT INTO procrastinate_workers (last_heartbeat) VALUES (now() - interval '1 hour') RETURNING id"
            )
        )
        job_id = await connection.scalar(
            sa.text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status, worker_id) "
                "VALUES ('default', 'mintrack:refresh_media', '{}', 'doing', :worker) RETURNING id"
            ),
            {"worker": worker_id},
        )
    app = get_worker_app()
    try:
        async with app.open_async():
            context = typing.cast("procrastinate.JobContext", types.SimpleNamespace(app=app))
            await tasks.retry_stalled_jobs.func(context, timestamp=0)
        async with database.engine.connect() as connection:
            status = await connection.scalar(
                sa.text("SELECT status FROM procrastinate_jobs WHERE id = :id"), {"id": job_id}
            )
        assert status == "todo"
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(sa.text("DELETE FROM procrastinate_jobs WHERE id = :id"), {"id": job_id})
            await connection.execute(sa.text("DELETE FROM procrastinate_workers WHERE id = :id"), {"id": worker_id})
