import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.accounts.managers import (
    available_timezones,
    canonical_timezone,
    database_timezone,
    timezone_choices,
)


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


def test_the_choices_name_each_zone_once_with_its_legacy_names() -> None:
    choices = timezone_choices()

    assert next(iter(choices)) == "UTC"
    assert "Asia/Calcutta" in choices["Asia/Kolkata"]
    assert "Europe/Kiev" in choices["Europe/Kyiv"]
    assert not {"Asia/Calcutta", "Europe/Kiev", "Etc/UTC"} & choices.keys()
    assert choices.keys() <= available_timezones() | {"UTC"}


async def test_postgresql_gets_a_name_it_knows(db_session: AsyncSession) -> None:
    assert await database_timezone(db_session, "Europe/Paris") == "Europe/Paris"
    assert await database_timezone(db_session, "US/Eastern") in {"US/Eastern", "America/New_York"}
    assert await database_timezone(db_session, "Mars/Olympus") is None
