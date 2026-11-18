import fastapi
import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.tmdb import media_id


async def show_page(signed_in: httpx.AsyncClient, title: str) -> tuple[int, dict]:
    await signed_in.get("/api/search", params={"query": title})
    tmdb_id = media_id("tv", title)
    show = (await signed_in.get(f"/api/shows/{tmdb_id}")).json()
    # The page loads a season's episodes when it opens.
    for season in show["seasons"]:
        path = f"/api/shows/{tmdb_id}/seasons/{season['season_number']}"
        season["episodes"] = (await signed_in.get(path)).json()["episodes"]
    return tmdb_id, show


def episode_id(show: dict, season: int, episode: int) -> str:
    episodes = next(s["episodes"] for s in show["seasons"] if s["season_number"] == season)
    return next(e["id"] for e in episodes if e["episode_number"] == episode)


async def test_marking_an_episode_adds_the_show_and_answers_its_tracking(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, show = await show_page(signed_in, "Marked Show")
    first = episode_id(show, 1, 1)

    marked = await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [first], "watched": True})
    unmarked = await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [first], "watched": False})

    assert marked.status_code == fastapi.status.HTTP_200_OK
    assert marked.json()["status"] == "watching"
    assert list(marked.json()["watched"]) == [first]
    assert unmarked.json() == {"status": "not_started", "watched": {}}


async def test_a_show_tracking_request_with_an_unknown_field_is_refused(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, _ = await show_page(signed_in, "Strict Show")

    response = await signed_in.put(f"/api/shows/{tmdb_id}/tracking", json={"stopped": True})

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_show_followed_with_nothing_watched_is_not_started(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, _ = await show_page(signed_in, "Fresh Show")

    followed = await signed_in.put(f"/api/shows/{tmdb_id}/tracking", json={"status": "watching"})
    aside = await signed_in.put(f"/api/shows/{tmdb_id}/tracking", json={"status": "watch_later"})

    assert followed.json()["status"] == "not_started"
    assert aside.json()["status"] == "watch_later"


async def test_episodes_of_another_show_are_rejected(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, _ = await show_page(signed_in, "Target Show")
    _, other = await show_page(signed_in, "Other Show")

    response = await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(other, 1, 1)], "watched": True}
    )

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_media_never_loaded_cannot_be_tracked(signed_in: httpx.AsyncClient) -> None:
    response = await signed_in.put(f"/api/shows/{media_id('tv', 'Never Loaded')}/tracking", json={"status": "watching"})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_the_library_lists_tracked_shows_with_progress_and_forgets_removed_ones(
    signed_in: httpx.AsyncClient,
) -> None:
    tmdb_id, show = await show_page(signed_in, "Library Show")
    removed_id, _ = await show_page(signed_in, "Removed Show")
    await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(show, 1, 1)], "watched": True}
    )
    await signed_in.put(f"/api/shows/{removed_id}/tracking", json={"status": "stopped"})
    await signed_in.delete(f"/api/shows/{removed_id}/tracking")

    library = (await signed_in.get("/api/library", params={"media_type": "tv"})).json()

    items = {item["tmdb_id"]: item for item in library}
    assert removed_id not in items
    assert items[tmdb_id]["added_at"] <= items[tmdb_id]["last_watched_at"]
    assert items[tmdb_id] | {"tmdb_id": 0, "added_at": None, "last_watched_at": None} == {
        "tmdb_id": 0,
        "media_type": "tv",
        "title": "Library Show",
        "poster_path": None,
        "status": "watching",
        "watched_count": 1,
        "aired_count": 5,
        "added_at": None,
        "last_watched_at": None,
    }


async def test_following_a_show_still_airing_defers_one_air_times_refresh(
    signed_in: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    airing, _ = await show_page(signed_in, "Airing Show")
    ended, _ = await show_page(signed_in, "Ended Show")
    for tmdb_id in (airing, airing, ended):
        await signed_in.put(f"/api/shows/{tmdb_id}/tracking", json={"status": "watching"})

    deferred = await db_session.scalars(
        sa.text(
            "SELECT media.tmdb_id FROM procrastinate_jobs JOIN media ON media.id::text = args->>'media_id' "
            "WHERE task_name = 'mintrack:refresh_show_air_times'"
        )
    )
    assert list(deferred) == [airing]


async def test_an_episode_airing_later_cannot_be_marked(signed_in: httpx.AsyncClient) -> None:
    # The fake show S02E03 airs in a week.
    tmdb_id, show = await show_page(signed_in, "Early Bird")

    response = await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(show, 2, 3)], "watched": True}
    )

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == "Some episodes have not aired yet"


async def test_the_show_page_names_the_next_episode_to_watch(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, show = await show_page(signed_in, "Next Up")
    before = show["next_episode"]
    await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(show, 1, 1)], "watched": True}
    )

    after = (await signed_in.get(f"/api/shows/{tmdb_id}")).json()["next_episode"]

    # S01E02, then S01E03, S02E01 and S02E02 aired; S02E03 airs in a week.
    assert before is None
    second = next(e for e in show["seasons"][0]["episodes"] if e["episode_number"] == 2)
    assert after == {**second, "remaining": 3}
