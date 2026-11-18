import fastapi
import httpx

from tests.fakes.tmdb import media_id


async def show_page(signed_in: httpx.AsyncClient, title: str) -> tuple[int, dict]:
    await signed_in.get("/api/search", params={"query": title})
    tmdb_id = media_id("tv", title)
    return tmdb_id, (await signed_in.get(f"/api/shows/{tmdb_id}")).json()


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
    assert unmarked.json() == {"status": "watch_later", "watched": {}}


async def test_episodes_of_another_show_are_rejected(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, _ = await show_page(signed_in, "Target Show")
    _, other = await show_page(signed_in, "Other Show")

    response = await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(other, 1, 1)], "watched": True}
    )

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_media_never_loaded_cannot_be_tracked(signed_in: httpx.AsyncClient) -> None:
    response = await signed_in.put(f"/api/shows/{media_id('tv', 'Never Loaded')}/tracking", json={"stopped": False})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_the_library_lists_tracked_shows_with_progress_and_forgets_removed_ones(
    signed_in: httpx.AsyncClient,
) -> None:
    tmdb_id, show = await show_page(signed_in, "Library Show")
    removed_id, _ = await show_page(signed_in, "Removed Show")
    await signed_in.post(
        f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [episode_id(show, 1, 1)], "watched": True}
    )
    await signed_in.put(f"/api/shows/{removed_id}/tracking", json={"stopped": True})
    await signed_in.delete(f"/api/shows/{removed_id}/tracking")

    library = (await signed_in.get("/api/library", params={"media_type": "tv"})).json()

    items = {item["tmdb_id"]: item for item in library}
    assert removed_id not in items
    assert items[tmdb_id] | {"tmdb_id": 0} == {
        "tmdb_id": 0,
        "media_type": "tv",
        "title": "Library Show",
        "poster_path": None,
        "status": "watching",
        "watched_count": 1,
        "aired_count": 5,
    }
