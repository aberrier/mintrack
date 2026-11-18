import functools

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mintrack.config import get_config
from mintrack.db.config import CONNECT_ARGS

# Seconds a request waits for a free pooled connection before failing.
POOL_TIMEOUT_SECONDS = 2


class DatabaseManager:
    def __init__(self, url: URL) -> None:
        self.engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            connect_args=CONNECT_ARGS,
            # Keeps bound parameters out of logs and error messages.
            hide_parameters=True,
        )
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


@functools.cache
def get_database() -> DatabaseManager:
    return DatabaseManager(get_config().database.url())
