import collections.abc
import contextlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.worker import tasks


class _Bound:
    """A database whose sessions are the test's, so jobs see its rolled-back data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @contextlib.asynccontextmanager
    async def session(self) -> collections.abc.AsyncGenerator[AsyncSession]:
        yield self._session


@pytest.fixture
def jobs_on_test_session(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Jobs run in the test's rolled-back session."""
    monkeypatch.setattr(tasks, "get_database", lambda: _Bound(db_session))
