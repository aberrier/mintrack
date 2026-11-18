import collections.abc
import contextlib
import io
import zipfile

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.imports.managers import ImportManager
from mintrack.db.models import ImportSource, User
from mintrack.server.api import imports as imports_api
from mintrack.worker import tasks
from tests.core.imports.fakes import FakeTMDB, seed_catalogue
from tests.core.imports.test_managers import TVTIME, YAMTRACK


class _Bound:
    """A database whose sessions are the test's, so the job sees its rolled-back data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @contextlib.asynccontextmanager
    async def session(self) -> collections.abc.AsyncGenerator[AsyncSession]:
        yield self._session


class ImportsDriver:
    """Someone importing their history from the profile page, through the API, with the worker running the jobs."""

    def __init__(self, client: httpx.AsyncClient, session: AsyncSession) -> None:
        self.client = client
        self.session = session

    async def upload(self, source: str, data: bytes, filename: str = "export.csv") -> httpx.Response:
        return await self.client.post("/api/imports", data={"source": source}, files={"file": (filename, data)})

    async def latest(self) -> dict | None:
        response = await self.client.get("/api/imports/latest")
        response.raise_for_status()
        return response.json()

    async def queued_jobs(self) -> list[str]:
        jobs = await self.session.scalars(
            sa.text("SELECT args->>'job_id' FROM procrastinate_jobs WHERE task_name = 'mintrack:imports.run'")
        )
        return list(jobs)

    async def report_once_run(self) -> dict:
        """Run the queued import as the worker would, then read its report."""
        (job_id,) = await self.queued_jobs()
        await tasks.run_import(job_id=job_id)
        job = await self.latest()
        assert job is not None
        assert job["status"] == "done", job
        return job["report"]


@pytest.fixture
def tmdb() -> FakeTMDB:
    """A TMDB knowing the catalogue's show and movie."""
    return FakeTMDB()


@pytest.fixture
async def imports(
    signed_in: httpx.AsyncClient, db_session: AsyncSession, tmdb: FakeTMDB, monkeypatch: pytest.MonkeyPatch
) -> ImportsDriver:
    await seed_catalogue(db_session)
    monkeypatch.setattr(tasks, "get_database", lambda: _Bound(db_session))
    monkeypatch.setattr(tasks, "get_tmdb_client", lambda: tmdb)
    return ImportsDriver(signed_in, db_session)


def zip_of(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


async def test_a_yamtrack_export_is_imported_in_the_background_with_a_report(imports: ImportsDriver) -> None:
    response = await imports.upload("yamtrack", YAMTRACK, "yamtrack.csv")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert await imports.queued_jobs() == [response.json()["id"]]
    report = await imports.report_once_run()
    assert (report["imported"], report["already_present"], report["unmatched_count"]) == (4, 0, 3)
    assert {"title": "Some Game", "reason": "unsupported"} in report["unmatched"]


async def test_a_tvtime_export_archive_is_imported(imports: ImportsDriver) -> None:
    response = await imports.upload("tvtime", zip_of("export/tracking-prod-records-v2.csv", TVTIME), "export.zip")

    assert response.status_code == 202
    report = await imports.report_once_run()
    assert report["imported"] == 3


async def test_a_second_import_waits_for_the_first(imports: ImportsDriver, db_session: AsyncSession) -> None:
    user = (await db_session.scalars(sa.select(User))).one()
    await ImportManager(db_session, FakeTMDB()).create(user, ImportSource.YAMTRACK, "running.csv", YAMTRACK)

    response = await imports.upload("yamtrack", YAMTRACK)

    assert response.status_code == 409
    assert (await imports.latest() or {})["filename"] == "running.csv"


@pytest.mark.parametrize(
    ("source", "data", "status"),
    [
        pytest.param("yamtrack", TVTIME, 422, id="TV Time file sent as Yamtrack"),
        pytest.param("tvtime", b"title\nMovie\n", 422, id="unknown CSV"),
        pytest.param("yamtrack", b"", 422, id="empty file"),
        pytest.param("trakt", YAMTRACK, 422, id="unknown source"),
    ],
)
async def test_files_that_are_not_an_export_are_refused(
    imports: ImportsDriver, source: str, data: bytes, status: int
) -> None:
    response = await imports.upload(source, data)

    assert response.status_code == status
    assert await imports.latest() is None
    assert await imports.queued_jobs() == []


async def test_a_file_over_the_size_limit_is_refused(imports: ImportsDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imports_api, "MAX_IMPORT_BYTES", len(YAMTRACK) - 1)

    response = await imports.upload("yamtrack", YAMTRACK)

    assert response.status_code == 413
    assert await imports.latest() is None


async def test_a_body_over_the_size_limit_is_refused_before_it_is_read(imports: ImportsDriver) -> None:
    response = await imports.client.post(
        "/api/imports",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(1024**3)},
    )

    assert response.status_code == 413
