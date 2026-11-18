import datetime as dt

import fastapi
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Media, MediaType, TrackingStatus, WatchedMovie
from tests.core.upcoming.factories import add_show, add_user, follow, watch
from tests.server.api.conftest import CreateUser, log_in

NOW = dt.datetime(2026, 11, 18, 15, tzinfo=dt.UTC)


def labels(response: httpx.Response) -> list[str]:
    return [
        entry["title"]
        if entry["media_type"] == "movie"
        else f"{entry['title']} {entry['season_number']}x{entry['episode_number']} {entry['episode_title']}"
        for entry in response.json()["entries"]
    ]


async def test_history_pages_through_episodes_and_movies_newest_first(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    alice = await create_user()
    await log_in(api)
    _, episodes = await add_show(db_session, {(0, 1): NOW, (1, 1): NOW, (1, 2): NOW, (1, 3): NOW}, title="Dark")
    movie = Media(media_type=MediaType.MOVIE, tmdb_id=1, title="Heat", refreshed_at=NOW)
    db_session.add(movie)
    await db_session.flush()
    db_session.add(WatchedMovie(user_id=alice.id, media_id=movie.id, watched_at=NOW - dt.timedelta(hours=1)))
    await watch(db_session, alice, episodes[1, 3], NOW - dt.timedelta(hours=2))
    # Marked together, as a whole season is.
    await watch(db_session, alice, episodes[1, 1], NOW - dt.timedelta(hours=3))
    await watch(db_session, alice, episodes[1, 2], NOW - dt.timedelta(hours=3))
    await watch(db_session, alice, episodes[0, 1], NOW - dt.timedelta(hours=4))
    await watch(db_session, await add_user(db_session), episodes[1, 1], NOW)

    first = await api.get("/api/history", params={"limit": 3})
    last = first.json()["entries"][-1]
    second = await api.get("/api/history", params={"limit": 3, "before": last["watched_at"], "before_id": last["id"]})
    before_the_tie = await api.get("/api/history", params={"before": last["watched_at"]})

    assert first.status_code == second.status_code == fastapi.status.HTTP_200_OK
    assert (labels(first)[:2], first.json()["has_more"]) == (["Heat", "Dark 1x3 Episode 1x3"], True)
    assert (labels(second)[1:], second.json()["has_more"]) == (["Dark 0x1 Episode 0x1"], False)
    # The episodes watched at the same time are split across the pages, each once.
    assert sorted([labels(first)[2], labels(second)[0]]) == ["Dark 1x1 Episode 1x1", "Dark 1x2 Episode 1x2"]
    assert labels(before_the_tie) == ["Dark 0x1 Episode 0x1"]
    assert first.json()["entries"][1]["poster_path"] == "/dark.jpg"


async def test_history_says_which_shows_the_user_finished(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    alice = await create_user()
    await log_in(api)
    finished, finished_episodes = await add_show(db_session, {(1, 1): NOW}, title="Done")
    watching, watching_episodes = await add_show(db_session, {(1, 1): NOW, (1, 2): NOW}, title="Going")
    await follow(db_session, alice, finished, TrackingStatus.FINISHED)
    await follow(db_session, alice, watching, TrackingStatus.WATCHING)
    # Another user's status is not the user's.
    await follow(db_session, await add_user(db_session), watching, TrackingStatus.FINISHED)
    await watch(db_session, alice, finished_episodes[1, 1], NOW - dt.timedelta(hours=1))
    await watch(db_session, alice, watching_episodes[1, 1], NOW - dt.timedelta(hours=2))

    response = await api.get("/api/history")

    assert [(entry["title"], entry["finished"]) for entry in response.json()["entries"]] == [
        ("Done", True),
        ("Going", False),
    ]
