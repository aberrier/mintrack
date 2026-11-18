import datetime as dt
import pathlib

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.imports.managers import STALE_AFTER, ImportInProgressError, ImportManager
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
from mintrack.integrations.tmdb.schemas import TMDBSearchResult
from tests.core.imports.fakes import FakeTMDB, seed_catalogue

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
    await manager.create(user, ImportSource.YAMTRACK, "c.csv", YAMTRACK)
    await db_session.refresh(running)
    assert running.status is ImportStatus.FAILED
    assert await db_session.scalar(sa.select(ImportJob.file).filter_by(id=running.id)) is None


async def test_latest_is_the_users_own_newest_job(db_session: AsyncSession, user: User) -> None:
    other = User(username="other")
    db_session.add(other)
    await db_session.flush()
    manager = ImportManager(db_session, FakeTMDB())
    await manager.create(other, ImportSource.YAMTRACK, "other.csv", YAMTRACK)

    assert await manager.latest(user) is None
