import collections.abc
import typing

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from .database import DatabaseManager, get_database

DatabaseDepType = typing.Annotated[DatabaseManager, fastapi.Depends(get_database)]


async def get_db_session(database: DatabaseDepType) -> collections.abc.AsyncGenerator[AsyncSession]:
    """A session for the request; endpoints commit explicitly, anything left uncommitted is rolled back."""
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        yield session


DbSessionDepType = typing.Annotated[AsyncSession, fastapi.Depends(get_db_session)]
