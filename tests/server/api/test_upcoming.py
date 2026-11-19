import datetime as dt
import zoneinfo

import fastapi
import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import TrackingStatus, User
from tests.core.upcoming.factories import add_show, follow, watch
from tests.server.api.conftest import CreateUser, log_in


@pytest_asyncio.fixture
async def alice(api: httpx.AsyncClient, create_user: CreateUser) -> User:
    """A signed-in user in Paris; reading needs no XSRF header."""
    user = await create_user()
    user.timezone = "Europe/Paris"
    await log_in(api)
    return user


async def test_someone_sees_coming_episodes_on_their_local_day(
    alice: User, db_session: AsyncSession, api: httpx.AsyncClient
) -> None:
    tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    show, episodes = await add_show(db_session, {(1, 1): tomorrow}, title="Severance")
    await follow(db_session, alice, show, TrackingStatus.WATCHING)

    response = await api.get("/api/upcoming")

    assert response.status_code == fastapi.status.HTTP_200_OK
    body = response.json()
    assert body["time_zone"] == "Europe/Paris"
    paris_day = tomorrow.astimezone(zoneinfo.ZoneInfo("Europe/Paris")).date().isoformat()
    assert body["days"] == [
        {
            "day": paris_day,
            "episodes": [
                {
                    "episode_id": str(episodes[1, 1].id),
                    "tmdb_id": show.tmdb_id,
                    "show_title": "Severance",
                    "poster_path": "/severance.jpg",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Episode 1x1",
                    "airstamp": tomorrow.isoformat().replace("+00:00", "Z"),
                    "day": paris_day,
                }
            ],
        }
    ]


async def test_an_empty_watch_list_says_whether_the_library_is_empty(
    alice: User, db_session: AsyncSession, api: httpx.AsyncClient
) -> None:
    before = (await api.get("/api/watch-list")).json()
    last_week = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=7)
    show, _ = await add_show(db_session, {(1, 1): last_week}, title="Stopped")
    await follow(db_session, alice, show, TrackingStatus.STOPPED)
    after = (await api.get("/api/watch-list")).json()

    assert before == {"episodes": [], "library_empty": True}
    assert after == {"episodes": [], "library_empty": False}


async def test_someone_sees_what_to_watch_next(alice: User, db_session: AsyncSession, api: httpx.AsyncClient) -> None:
    last_week = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=7)
    show, episodes = await add_show(db_session, {(1, 1): last_week, (1, 2): last_week}, title="Andor")
    fresh, fresh_episodes = await add_show(db_session, {(1, 1): last_week, (2, 1): None}, title="Fresh")
    await follow(db_session, alice, show, TrackingStatus.WATCHING)
    await follow(db_session, alice, fresh, TrackingStatus.NOT_STARTED)
    await watch(db_session, alice, episodes[1, 1], dt.datetime.now(dt.UTC))

    watch_list = await api.get("/api/watch-list")

    assert watch_list.status_code == fastapi.status.HTTP_200_OK
    cards = watch_list.json()["episodes"]
    assert [
        (episode["show_title"], episode["episode_number"], episode["remaining"], episode["section"])
        for episode in cards
    ] == [("Andor", 2, 0, "next"), ("Fresh", 1, 0, "not_started")]
    # The episode after the card's, across the season end; none after the last one.
    assert cards[0]["following"] is None
    assert cards[1]["following"] == {
        "id": str(fresh_episodes[2, 1].id),
        "season_number": 2,
        "episode_number": 1,
        "title": fresh_episodes[2, 1].title,
        "air_date": None,
        "airstamp": None,
    }
