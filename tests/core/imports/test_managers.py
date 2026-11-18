import asyncio
import datetime as dt
import pathlib
import typing

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.imports.managers import PROGRESS_EVERY, STALE_AFTER, ImportInProgressError, ImportManager
from mintrack.core.imports.parsers import ImportFileError
from mintrack.db.models import (
    Episode,
    ImportJob,
    ImportSource,
    ImportStatus,
    Media,
    MediaType,
    TrackingStatus,
    User,
    UserMedia,
    WatchedEpisode,
    WatchedMovie,
)
from mintrack.integrations.tmdb.client import ExternalSource
from mintrack.integrations.tmdb.schemas import TMDBSearchResult
from tests.core.imports.fakes import MOVIE_IMDB_ID, FakeTMDB, seed_catalogue

DATA = pathlib.Path(__file__).parent / "data"

YAMTRACK = (DATA / "yamtrack.csv").read_bytes()

TVTIME = (DATA / "tracking-prod-records-v2.csv").read_bytes()

TVTIME_TITLES_ONLY = (DATA / "tracking-prod-records.csv").read_bytes()


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(username="viewer", timezone="Europe/Paris")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def catalogue(db_session: AsyncSession) -> tuple[Media, Media]:
    return await seed_catalogue(db_session)


async def run_import(
    session: AsyncSession, user: User, source: ImportSource, data: bytes, tmdb: FakeTMDB | None = None
) -> ImportJob:
    manager = ImportManager(session, tmdb or FakeTMDB())
    job = await manager.create(user, source, "export", data)
    await session.commit()
    await manager.run(job.id)
    await session.refresh(job)
    return job


async def watched_episode_dates(session: AsyncSession, user: User) -> list[dt.datetime]:
    return list(
        await session.scalars(
            sa.select(WatchedEpisode.watched_at).filter_by(user_id=user.id).order_by(WatchedEpisode.watched_at)
        )
    )


async def test_yamtrack_import_reports_and_keeps_the_watch_dates(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    show, movie = catalogue

    job = await run_import(db_session, user, ImportSource.YAMTRACK, YAMTRACK)

    assert job.status is ImportStatus.DONE
    assert (job.total, job.processed) == (7, 7)
    assert job.report == {
        # The show, its two episodes and the movie.
        "imported": 4,
        "already_present": 0,
        "unmatched_count": 3,
        "unmatched": [
            {"title": "Northern Lights S01E09", "reason": "episode_not_found"},
            {"title": "Unknown Movie", "reason": "not_found"},
            {"title": "Some Game", "reason": "unsupported"},
        ],
    }
    assert await watched_episode_dates(db_session, user) == [
        dt.datetime(2024, 2, 8, 23, tzinfo=dt.UTC),
        dt.datetime(2024, 2, 10, 21, 30, tzinfo=dt.UTC),
    ]
    assert await db_session.scalar(sa.select(WatchedMovie.watched_at).filter_by(media_id=movie.id)) == dt.datetime(
        2024, 3, 1, 20, tzinfo=dt.UTC
    )
    statuses = dict((await db_session.execute(sa.select(UserMedia.media_id, UserMedia.status))).all())
    assert statuses == {show.id: TrackingStatus.WATCHING, movie.id: TrackingStatus.WATCHED}


@pytest.mark.parametrize(("source", "data"), [(ImportSource.YAMTRACK, YAMTRACK), (ImportSource.TVTIME, TVTIME)])
async def test_importing_the_same_file_again_adds_nothing(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media], source: ImportSource, data: bytes
) -> None:
    first = await run_import(db_session, user, source, data)
    watches = await watched_episode_dates(db_session, user)

    second = await run_import(db_session, user, source, data)

    assert second.report is not None
    assert first.report is not None
    assert second.report["imported"] == 0
    assert second.report["already_present"] == first.report["imported"] + first.report["already_present"]
    assert await watched_episode_dates(db_session, user) == watches


async def test_tvtime_import_matches_by_tvdb_id_and_keeps_the_first_watch(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    job = await run_import(db_session, user, ImportSource.TVTIME, TVTIME)

    assert job.report == {
        # The show, the first watch of its first episode, the movie; the rewatch is already there.
        "imported": 3,
        "already_present": 1,
        "unmatched_count": 1,
        "unmatched": [{"title": "Unknown Show", "reason": "not_found"}],
    }
    assert await watched_episode_dates(db_session, user) == [dt.datetime(2023, 1, 2, 20, tzinfo=dt.UTC)]


async def test_tvtime_rows_without_show_id_resolve_the_show_once_by_episode_id(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    tmdb = FakeTMDB()

    job = await run_import(db_session, user, ImportSource.TVTIME, TVTIME_TITLES_ONLY, tmdb)

    assert job.report is not None
    assert job.report["imported"] == 2
    assert tmdb.calls == 1


async def test_tvtime_episodes_without_numbers_are_found_once_per_episode_id(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    tmdb = FakeTMDB()
    rows = "".join(f"watch-episode-{day},5001,Northern Lights,,9012,,,2023-01-{day:02} 21:00:00\n" for day in (3, 4))
    data = b"key,s_id,series_name,is_followed,episode_id,season_number,episode_number,created_at\n" + rows.encode()

    job = await run_import(db_session, user, ImportSource.TVTIME, data, tmdb)

    assert job.report is not None
    assert (job.report["imported"], job.report["already_present"]) == (1, 1)
    # The episode by its TVDB id, then the show by its TVDB id.
    assert tmdb.calls == 2


async def test_tvtime_episodes_numbered_differently_on_tvdb_are_found_by_episode_id(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    # TVDB's season 3 episode 1 is TMDB's season 2 episode 1 (TVDB episode id 9021).
    data = (
        b"key,s_id,series_name,is_followed,episode_id,season_number,episode_number,created_at\n"
        b"watch-episode-1,5001,Northern Lights,,9021,3,1,2023-01-05 21:00:00\n"
    )

    job = await run_import(db_session, user, ImportSource.TVTIME, data)

    assert job.report is not None
    assert (job.report["imported"], job.report["unmatched"]) == (1, [])
    watched = await db_session.scalar(
        sa.select(Episode.season_number).join(WatchedEpisode).where(WatchedEpisode.user_id == user.id)
    )
    assert watched == 2


async def test_rows_are_unmatched_when_tmdb_is_unavailable(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    job = await run_import(db_session, user, ImportSource.TVTIME, TVTIME, FakeTMDB(down=True))

    assert job.status is ImportStatus.DONE
    assert job.report is not None
    assert {item["reason"] for item in job.report["unmatched"]} == {"tmdb_unavailable"}


async def test_media_already_in_the_library_keep_their_status(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    show, _ = catalogue
    now = dt.datetime.now(dt.UTC)
    entry = UserMedia(user_id=user.id, media_id=show.id, status=TrackingStatus.STOPPED, added_at=now, updated_at=now)
    db_session.add(entry)
    data = YAMTRACK.splitlines()[0] + b"\n1001,tmdb,tv,Northern Lights,,,,,,Completed,,,,\n"

    job = await run_import(db_session, user, ImportSource.YAMTRACK, data)

    await db_session.refresh(entry)
    assert entry.status is TrackingStatus.STOPPED
    assert job.report is not None
    assert job.report["already_present"] == 1


async def test_shows_dropped_in_yamtrack_stay_stopped_after_their_episodes(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    show, _ = catalogue
    data = YAMTRACK.splitlines()[0] + (
        b"\n1001,tmdb,tv,Northern Lights,,,,,,Dropped,,,,\n1001,tmdb,episode,Northern Lights,,1,1,,,,,2024-02-09,,\n"
    )

    await run_import(db_session, user, ImportSource.YAMTRACK, data)

    assert await db_session.scalar(sa.select(UserMedia.status).filter_by(media_id=show.id)) is TrackingStatus.STOPPED


@pytest.mark.parametrize(
    ("flags", "status"),
    [("false,true,false", TrackingStatus.STOPPED), ("false,false,true", TrackingStatus.WATCH_LATER)],
)
async def test_tvtime_archived_and_for_later_shows_stay_set_aside_after_their_episodes(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media], flags: str, status: TrackingStatus
) -> None:
    show, _ = catalogue
    data = (
        "key,s_id,series_name,is_followed,is_archived,is_for_later,episode_id,season_number,episode_number,created_at\n"
        f"user-series-1,{show.tvdb_id},Northern Lights,{flags},,,,2023-01-01 10:00:00\n"
        f"watch-episode-1,{show.tvdb_id},Northern Lights,,,,9011,1,1,2023-01-02 20:00:00\n"
    ).encode()

    await run_import(db_session, user, ImportSource.TVTIME, data)

    assert await db_session.scalar(sa.select(UserMedia.status).filter_by(media_id=show.id)) is status
    assert len(await watched_episode_dates(db_session, user)) == 1


async def test_a_show_followed_with_nothing_watched_is_not_started(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    show, _ = catalogue
    data = YAMTRACK.splitlines()[0] + b"\n1001,tmdb,tv,Northern Lights,,,,,,Planning,,,,\n"

    await run_import(db_session, user, ImportSource.YAMTRACK, data)

    status = await db_session.scalar(sa.select(UserMedia.status).filter_by(media_id=show.id))
    assert status is TrackingStatus.NOT_STARTED


async def test_a_movie_dated_far_in_the_future_is_watched_when_the_import_ran(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    _, movie = catalogue
    data = YAMTRACK.splitlines()[0] + b"\n2001,tmdb,movie,Glass Harbor,,,,,1,Completed,,9999-12-31T23:59:59-12:00,,\n"

    job = await run_import(db_session, user, ImportSource.YAMTRACK, data)

    assert job.status is ImportStatus.DONE
    watched_at = await db_session.scalar(sa.select(WatchedMovie.watched_at).filter_by(media_id=movie.id))
    assert watched_at is not None
    assert watched_at <= dt.datetime.now(dt.UTC)


async def test_anime_without_episode_rows_get_their_progress_in_airing_order(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    data = YAMTRACK.splitlines()[0] + b"\n21,mal,anime,Northern Lights,,,,,3,In progress,,2024-05-01,,\n"

    await run_import(db_session, user, ImportSource.YAMTRACK, data)

    watched = await db_session.execute(
        sa.select(Episode.season_number, Episode.episode_number)
        .join(WatchedEpisode, WatchedEpisode.episode_id == Episode.id)
        .filter(WatchedEpisode.user_id == user.id)
        .order_by(Episode.season_number, Episode.episode_number)
    )
    assert watched.all() == [(1, 1), (1, 2), (1, 3)]


async def test_the_file_is_dropped_when_the_job_ends(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    job = await run_import(db_session, user, ImportSource.YAMTRACK, YAMTRACK)

    assert await db_session.scalar(sa.select(ImportJob.file).filter_by(id=job.id)) is None


async def test_a_failed_job_drops_its_file(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    class BrokenTMDB(FakeTMDB):
        async def search(self, query: str, media_type: MediaType | None = None) -> list[TMDBSearchResult]:
            raise RuntimeError

    job = await run_import(
        db_session, user, ImportSource.TVTIME, TVTIME_TITLES_ONLY.replace(b"9012", b"1"), BrokenTMDB()
    )

    assert job.status is ImportStatus.FAILED
    assert job.finished_at is not None
    assert await db_session.scalar(sa.select(ImportJob.file).filter_by(id=job.id)) is None


async def test_an_invalid_file_is_refused_and_not_stored(db_session: AsyncSession, user: User) -> None:
    with pytest.raises(ImportFileError):
        await ImportManager(db_session, FakeTMDB()).create(user, ImportSource.YAMTRACK, "x.csv", TVTIME)

    assert await db_session.scalar(sa.select(sa.func.count()).select_from(ImportJob)) == 0


async def test_one_import_at_a_time_unless_the_running_one_was_lost(db_session: AsyncSession, user: User) -> None:
    manager = ImportManager(db_session, FakeTMDB())
    running = await manager.create(user, ImportSource.YAMTRACK, "a.csv", YAMTRACK)

    with pytest.raises(ImportInProgressError):
        await manager.create(user, ImportSource.YAMTRACK, "b.csv", YAMTRACK)

    running.updated_at -= STALE_AFTER + dt.timedelta(seconds=1)
    await db_session.flush()
    # Still queued: a worker will run it, however long the queue.
    with pytest.raises(ImportInProgressError):
        await manager.create(user, ImportSource.YAMTRACK, "b.csv", YAMTRACK)

    await drop_task(db_session, running)
    await manager.create(user, ImportSource.YAMTRACK, "c.csv", YAMTRACK)
    await db_session.refresh(running)
    assert running.status is ImportStatus.FAILED
    assert await db_session.scalar(sa.select(ImportJob.file).filter_by(id=running.id)) is None


async def drop_task(session: AsyncSession, job: ImportJob) -> None:
    """The job's task leaves the queue, as when the queue is cleared."""
    await session.execute(
        sa.text("DELETE FROM procrastinate_jobs WHERE queueing_lock = :lock"), {"lock": f"import:{job.id}"}
    )


async def test_a_job_whose_worker_stopped_starts_again(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    manager = ImportManager(db_session, FakeTMDB())
    job = await manager.create(user, ImportSource.YAMTRACK, "a.csv", YAMTRACK)
    job.status = ImportStatus.RUNNING
    await db_session.commit()

    await manager.run(job.id)

    await db_session.refresh(job)
    assert job.status is ImportStatus.DONE


async def test_latest_is_the_users_own_newest_job(db_session: AsyncSession, user: User) -> None:
    other = User(username="other")
    db_session.add(other)
    await db_session.flush()
    manager = ImportManager(db_session, FakeTMDB())
    await manager.create(other, ImportSource.YAMTRACK, "other.csv", YAMTRACK)

    assert await manager.latest(user) is None


async def test_another_season_entry_of_an_anime_matched_to_the_same_show_is_left_to_check(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    class SeasonTitlesTMDB(FakeTMDB):
        async def search(self, query: str, media_type: MediaType | None = None) -> list[TMDBSearchResult]:
            return await super().search(query.removesuffix(" Season 2"), media_type)

    data = YAMTRACK.splitlines()[0] + (
        b"\n21,mal,anime,Northern Lights,,,,,2,In progress,,2024-05-01,,"
        b"\n22,mal,anime,Northern Lights Season 2,,,,,3,In progress,,2024-06-01,,\n"
    )

    job = await run_import(db_session, user, ImportSource.YAMTRACK, data, SeasonTitlesTMDB())

    assert job.report is not None
    assert job.report["unmatched"] == [{"title": "Northern Lights Season 2", "reason": "to_check"}]
    assert len(await watched_episode_dates(db_session, user)) == 2


async def test_a_job_interrupted_by_a_shutdown_is_failed(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    class ShutdownTMDB(FakeTMDB):
        async def search(self, query: str, media_type: MediaType | None = None) -> list[TMDBSearchResult]:
            raise asyncio.CancelledError

    manager = ImportManager(db_session, ShutdownTMDB())
    job = await manager.create(user, ImportSource.TVTIME, "export", TVTIME_TITLES_ONLY.replace(b"9012", b"1"))
    await db_session.commit()

    with pytest.raises(asyncio.CancelledError):
        await manager.run(job.id)

    await db_session.refresh(job)
    assert job.status is ImportStatus.FAILED


async def test_a_lost_job_reads_as_failed(db_session: AsyncSession, user: User) -> None:
    manager = ImportManager(db_session, FakeTMDB())
    job = await manager.create(user, ImportSource.YAMTRACK, "a.csv", YAMTRACK)
    job.status, job.updated_at = ImportStatus.RUNNING, job.updated_at - STALE_AFTER - dt.timedelta(seconds=1)
    await db_session.flush()
    await drop_task(db_session, job)

    latest = await manager.latest(user)

    assert latest is not None
    await db_session.refresh(latest)
    assert latest.status is ImportStatus.FAILED


async def test_progress_is_committed_every_50_rows_so_a_failure_keeps_the_rows_before_it(
    db_session: AsyncSession, user: User, catalogue: tuple[Media, Media]
) -> None:
    class BrokenTMDB(FakeTMDB):
        async def find(self, external_id: str, source: ExternalSource) -> dict[str, typing.Any]:
            if external_id == "tt9999999":
                raise RuntimeError
            return await super().find(external_id, source)

    movie_id, user_id = catalogue[1].id, user.id
    header = TVTIME.splitlines()[0] + b",imdb_id"
    # A movie found by its IMDb id under another title, rewatches up to the first commit, then an episode watched for
    # the first time and a movie whose lookup fails.
    rows = [b",,,,,,,Glass Harbour (Director's Cut),watch,2023-02-01 22:00:00,,," + MOVIE_IMDB_ID.encode()]
    rows += [
        f"rewatch-episode-{index}-9011,5001,Northern Lights,,9011,1,1,,,,,2023-03-01 20:{index:02}:00,".encode()
        for index in range(PROGRESS_EVERY - 1)
    ]
    rows += [
        b"watch-episode-1-9012,5001,Northern Lights,,9012,1,2,,,,,2023-04-01 20:00:00,",
        b",,,,,,,Lost Movie,watch,2023-05-01 22:00:00,,,tt9999999",
    ]

    job = await run_import(db_session, user, ImportSource.TVTIME, b"\n".join([header, *rows]), BrokenTMDB())

    assert (job.status, job.total, job.processed) == (ImportStatus.FAILED, PROGRESS_EVERY + 2, PROGRESS_EVERY)
    assert await db_session.scalar(sa.select(WatchedMovie.watched_at).filter_by(media_id=movie_id)) == dt.datetime(
        2023, 2, 1, 22, tzinfo=dt.UTC
    )
    episodes = await db_session.scalars(sa.select(WatchedEpisode.watched_at).filter_by(user_id=user_id))
    assert list(episodes) == [dt.datetime(2023, 3, 1, 20, tzinfo=dt.UTC)]
