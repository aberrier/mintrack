import datetime as dt

import fastapi
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Media, MediaType, TrackingStatus, User, UserMedia, WatchedMovie
from tests.core.upcoming.factories import add_show, follow, watch
from tests.server.api.conftest import CreateUser, log_in

NOW = dt.datetime.now(dt.UTC)


def days_ago(days: int) -> dt.datetime:
    return NOW - dt.timedelta(days=days)


def moment(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value else None


@pytest_asyncio.fixture
async def alice(api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession) -> User:
    """A signed-in user with four shows: two watched, one not started, one stopped before starting."""
    user = await create_user()
    await log_in(api)
    shows = {
        "Bravo": (TrackingStatus.WATCHING, days_ago(10), days_ago(1)),
        "alpha": (TrackingStatus.UP_TO_DATE, days_ago(5), days_ago(3)),
        "Charlie": (TrackingStatus.NOT_STARTED, days_ago(2), None),
        "Delta": (TrackingStatus.STOPPED, days_ago(20), None),
    }
    for title, (status, added_at, watched_at) in shows.items():
        show, episodes = await add_show(db_session, {(1, 1): days_ago(30)}, title=title)
        await follow(db_session, user, show, status, at=added_at)
        if watched_at:
            await watch(db_session, user, episodes[1, 1], watched_at)
    return user


async def titles(api: httpx.AsyncClient, **params: str) -> list[str]:
    response = await api.get("/api/library", params={"media_type": "tv", **params})
    assert response.status_code == fastapi.status.HTTP_200_OK
    return [item["title"] for item in response.json()]


@pytest.mark.usefixtures("alice")
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ["Bravo", "alpha", "Charlie", "Delta"]),
        ({"sort": "last_added"}, ["Charlie", "alpha", "Bravo", "Delta"]),
        ({"sort": "title"}, ["alpha", "Bravo", "Charlie", "Delta"]),
        ({"status": "not_started"}, ["Charlie"]),
        ({"status": "stopped"}, ["Delta"]),
        ({"status": "watching", "sort": "title"}, ["Bravo"]),
    ],
)
async def test_the_library_sorts_and_filters_by_progress(
    api: httpx.AsyncClient, params: dict[str, str], expected: list[str]
) -> None:
    assert await titles(api, **params) == expected


async def test_library_items_tell_when_they_were_added_and_last_watched(
    alice: User, api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    watched, later = (
        Media(media_type=MediaType.MOVIE, tmdb_id=tmdb_id, title=title, refreshed_at=NOW)
        for tmdb_id, title in ((1, "Heat"), (2, "Ronin"))
    )
    db_session.add_all([watched, later])
    await db_session.flush()
    db_session.add_all(
        [
            UserMedia(
                user_id=alice.id,
                media_id=watched.id,
                status=TrackingStatus.WATCHED,
                added_at=days_ago(9),
                updated_at=NOW,
            ),
            UserMedia(
                user_id=alice.id,
                media_id=later.id,
                status=TrackingStatus.WATCH_LATER,
                added_at=days_ago(1),
                updated_at=NOW,
            ),
            WatchedMovie(user_id=alice.id, media_id=watched.id, watched_at=days_ago(4)),
        ]
    )
    await db_session.flush()

    movies = (await api.get("/api/library", params={"media_type": "movie"})).json()
    later_titles = await titles(api, media_type="movie", status="watch_later")

    assert [(movie["title"], moment(movie["added_at"]), moment(movie["last_watched_at"])) for movie in movies] == [
        ("Heat", days_ago(9), days_ago(4)),
        ("Ronin", days_ago(1), None),
    ]
    assert later_titles == ["Ronin"]
