import collections.abc
import datetime as dt
import os
import pathlib

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

import mintrack.config
from mintrack.config import DatabaseConfig, get_config
from mintrack.core.catalog.managers import CatalogManager
from mintrack.db import alembic
from mintrack.db.database import DatabaseManager, get_database
from mintrack.db.models import Episode, Media, MediaType, User
from mintrack.integrations.tmdb.client import TMDBClient
from mintrack.integrations.tmdb.config import TMDBConfig
from mintrack.worker.app import get_worker_app
from tests.fakes.tmdb import FakeTMDB

pytest_plugins = ["tests.push_service", "tests.fakes.jellyfin"]

# Tests see the variables of pyproject.toml and those they set, never a developer's .env.
mintrack.config.ENV_FILE = None

DATABASE_PASSWORD = "p@ss/w:rd%#value"


def recreate_database(config: DatabaseConfig, name: str) -> URL:
    """Create an empty database next to the configured one and return its URL."""
    admin_engine = sa.create_engine(config.url(), isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
    quoted = admin_engine.dialect.identifier_preparer.quote(name)
    with admin_engine.connect() as connection:
        connection.execute(sa.text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
        connection.execute(sa.text(f"CREATE DATABASE {quoted}"))
    admin_engine.dispose()
    return config.url(database=name)


def drop_database(config: DatabaseConfig, name: str) -> None:
    admin_engine = sa.create_engine(config.url(), isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
    quoted = admin_engine.dialect.identifier_preparer.quote(name)
    with admin_engine.connect() as connection:
        connection.execute(sa.text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> collections.abc.Generator[URL]:
    """A migrated `test_<name>` database, configured as the app's database for the rest of the session."""
    config = get_config().database
    name = f"test_{config.name}"
    url = recreate_database(config, name)
    alembic.upgrade(url)
    with pytest.MonkeyPatch.context() as session_patch:
        session_patch.setenv("MINTRACK__DATABASE__NAME", name)
        get_config.cache_clear()
        get_database.cache_clear()
        get_worker_app.cache_clear()
        yield url
    get_config.cache_clear()
    get_database.cache_clear()
    get_worker_app.cache_clear()
    drop_database(config, name)


@pytest_asyncio.fixture(scope="session")
async def database(test_database_url: URL) -> collections.abc.AsyncGenerator[DatabaseManager]:
    manager = get_database()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def db_session(database: DatabaseManager) -> collections.abc.AsyncGenerator[AsyncSession]:
    """A session whose work is rolled back after the test, commits included (they become savepoints)."""
    async with database.engine.connect() as connection, connection.begin() as transaction:
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> collections.abc.Generator[pytest.MonkeyPatch]:
    """Only the variables a test sets, and no .env file in the working directory."""
    for name in list(os.environ):
        if name.upper().startswith("MINTRACK__"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINTRACK__DATABASE__HOST", "db")
    monkeypatch.setenv("MINTRACK__DATABASE__USER", "mintrack")
    monkeypatch.setenv("MINTRACK__DATABASE__PASSWORD", DATABASE_PASSWORD)
    monkeypatch.setenv("MINTRACK__DATABASE__NAME", "mintrack")
    get_config.cache_clear()
    yield monkeypatch
    get_config.cache_clear()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(username="viewer")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def fake_tmdb() -> FakeTMDB:
    return FakeTMDB()


def make_tmdb_client(fake: FakeTMDB, *, api_key: str | None = "test-key") -> TMDBClient:
    return TMDBClient(TMDBConfig(api_key=api_key), transport=httpx.ASGITransport(app=fake.build_app()))


@pytest.fixture
def tmdb(fake_tmdb: FakeTMDB) -> TMDBClient:
    """A client of the fake TMDB, whose searches give each test its own media."""
    return make_tmdb_client(fake_tmdb)


async def cached_media(
    session: AsyncSession, tmdb: TMDBClient, title: str, media_type: MediaType = MediaType.TV
) -> Media:
    """The show (or movie) the fake TMDB serves for `title`, cached as its page would."""
    result = next(result for result in await tmdb.search(title) if result.media_type == media_type)
    return await CatalogManager(session, tmdb).get_or_fetch(media_type, result.id, dt.datetime.now(dt.UTC))


async def episodes_of(session: AsyncSession, media: Media) -> dict[tuple[int, int], Episode]:
    episodes = await session.scalars(sa.select(Episode).where(Episode.media_id == media.id))
    return {(episode.season_number, episode.episode_number): episode for episode in episodes}
