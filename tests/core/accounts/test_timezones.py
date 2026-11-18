import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.managers import canonical_timezone, database_timezone


@pytest.mark.parametrize(
    ("name", "canonical"),
    [
        ("Asia/Calcutta", "Asia/Kolkata"),
        ("US/Eastern", "America/New_York"),
        ("Europe/Kiev", "Europe/Kyiv"),
        ("Europe/Paris", "Europe/Paris"),
    ],
)
def test_a_legacy_name_has_the_current_name_of_its_zone(name: str, canonical: str) -> None:
    assert canonical_timezone(name) == canonical


async def test_postgresql_gets_a_name_it_knows(db_session: AsyncSession) -> None:
    assert await database_timezone(db_session, "Europe/Paris") == "Europe/Paris"
    assert await database_timezone(db_session, "US/Eastern") in {"US/Eastern", "America/New_York"}
    assert await database_timezone(db_session, "Mars/Olympus") is None
