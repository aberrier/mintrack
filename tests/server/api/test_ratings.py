import fastapi
import httpx
import pytest

from mintrack.db.models.rating import MAX_REVIEW_LENGTH
from tests.fakes.tmdb import media_id
from tests.server.api.conftest import CreateUser, log_in, xsrf
from tests.server.api.test_tracking import episode_id, show_page


async def test_a_show_rating_is_saved_changed_and_removed(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, _ = await show_page(signed_in, "Rated Show")

    first = await signed_in.put(f"/api/shows/{tmdb_id}/rating", json={"stars": 3})
    changed = await signed_in.put(f"/api/shows/{tmdb_id}/rating", json={"stars": 5, "review": "  Better on rewatch. "})
    shown = (await signed_in.get(f"/api/shows/{tmdb_id}")).json()
    removed = await signed_in.delete(f"/api/shows/{tmdb_id}/rating")

    assert (first.json()["stars"], first.json()["review"]) == (3, "")
    assert (changed.json()["stars"], changed.json()["review"]) == (5, "Better on rewatch.")
    assert shown["rating"]["stars"] == 5
    assert (shown["vote_average"], shown["vote_count"]) == (8.25, 1234)
    assert removed.status_code == fastapi.status.HTTP_204_NO_CONTENT
    assert (await signed_in.get(f"/api/shows/{tmdb_id}")).json()["rating"] is None


async def test_a_movie_rating_shows_on_its_page_and_in_the_history(signed_in: httpx.AsyncClient) -> None:
    await signed_in.get("/api/search", params={"query": "Rated Movie"})
    tmdb_id = media_id("movie", "Rated Movie")
    await signed_in.get(f"/api/movies/{tmdb_id}")
    await signed_in.put(f"/api/movies/{tmdb_id}/tracking", json={"watched": True})

    await signed_in.put(f"/api/movies/{tmdb_id}/rating", json={"stars": 2, "review": "Too long."})

    movie = (await signed_in.get(f"/api/movies/{tmdb_id}")).json()
    history = (await signed_in.get("/api/history")).json()["entries"]
    assert (movie["rating"]["stars"], movie["rating"]["review"]) == (2, "Too long.")
    assert [(entry["tmdb_id"], entry["rating"]) for entry in history] == [(tmdb_id, 2)]
    await signed_in.delete(f"/api/movies/{tmdb_id}/rating")
    assert (await signed_in.get(f"/api/movies/{tmdb_id}")).json()["rating"] is None


async def test_episode_ratings_show_in_the_history(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, show = await show_page(signed_in, "History Rated Show")
    first, second = episode_id(show, 1, 1), episode_id(show, 1, 2)
    await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [first, second], "watched": True})

    await signed_in.put(f"/api/episodes/{first}/rating", json={"stars": 1})
    await signed_in.put(f"/api/episodes/{second}/rating", json={"stars": 4})
    await signed_in.delete(f"/api/episodes/{second}/rating")

    history = (await signed_in.get("/api/history")).json()["entries"]
    assert {entry["id"]: entry["rating"] for entry in history} == {first: 1, second: None}


@pytest.mark.parametrize(
    "body",
    [{"stars": 0}, {"stars": 6}, {"stars": 3, "review": "x" * (MAX_REVIEW_LENGTH + 1)}, {"stars": 3, "score": 9}],
)
async def test_ratings_out_of_bounds_are_refused(signed_in: httpx.AsyncClient, body: dict) -> None:
    tmdb_id, _ = await show_page(signed_in, "Bounded Show")

    response = await signed_in.put(f"/api/shows/{tmdb_id}/rating", json=body)

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_ratings_are_private_to_each_user(signed_in: httpx.AsyncClient, create_user: CreateUser) -> None:
    tmdb_id, show = await show_page(signed_in, "Private Show")
    first = episode_id(show, 1, 1)
    await signed_in.put(f"/api/shows/{tmdb_id}/rating", json={"stars": 5})
    await signed_in.put(f"/api/episodes/{first}/rating", json={"stars": 5})
    await create_user("bob")
    await log_in(signed_in, "bob")
    signed_in.headers.update(xsrf(signed_in))

    assert (await signed_in.get(f"/api/shows/{tmdb_id}")).json()["rating"] is None
    assert (await signed_in.get(f"/api/episodes/{first}")).json()["rating"] is None


async def test_media_never_loaded_cannot_be_rated(signed_in: httpx.AsyncClient) -> None:
    response = await signed_in.put(f"/api/movies/{media_id('movie', 'Never Loaded')}/rating", json={"stars": 3})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
