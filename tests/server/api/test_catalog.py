import datetime as dt

import fastapi
import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Media, MediaType
from mintrack.integrations.tmdb.client import get_tmdb_client
from tests.conftest import make_tmdb_client
from tests.fakes.tmdb import MAX_ID, FakeTMDB, media_id


async def test_search_finds_shows_and_movies_with_the_users_status(signed_in: httpx.AsyncClient) -> None:
    show_id = media_id("tv", "Orbit Kitchen")
    await signed_in.get(f"/api/shows/{show_id}")
    await signed_in.put(f"/api/shows/{show_id}/tracking", json={"stopped": False})

    response = await signed_in.get("/api/search", params={"query": "Orbit Kitchen"})

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert [(r["media_type"], r["year"], r["tracking_status"]) for r in response.json()] == [
        ("tv", 2024, "watch_later"),
        ("movie", None, None),
    ]


async def test_a_show_page_lists_seasons_with_specials_last(signed_in: httpx.AsyncClient) -> None:
    await signed_in.get("/api/search", params={"query": "Night Shift"})

    response = await signed_in.get(f"/api/shows/{media_id('tv', 'Night Shift')}")

    show = response.json()
    assert response.status_code == fastapi.status.HTTP_200_OK
    assert (show["title"], show["tracking"]) == ("Night Shift", None)
    assert [(s["season_number"], len(s["episodes"])) for s in show["seasons"]] == [(1, 3), (2, 3), (0, 1)]


async def test_a_stale_page_defers_one_refresh_in_its_transaction(
    signed_in: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    show_id = media_id("tv", "Stale Show")
    await signed_in.get(f"/api/shows/{show_id}")
    await db_session.execute(
        sa.update(Media)
        .where(Media.tmdb_id == show_id, Media.media_type == MediaType.TV)
        .values(refreshed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=2))
    )
    media = await db_session.scalar(sa.select(Media.id).where(Media.tmdb_id == show_id))
    jobs = sa.text("SELECT count(*) FROM procrastinate_jobs WHERE status = 'todo' AND args->>'media_id' = :id")

    for _ in range(2):
        assert (await signed_in.get(f"/api/shows/{show_id}")).status_code == fastapi.status.HTTP_200_OK

    assert await db_session.scalar(jobs, {"id": str(media)}) == 1


async def test_tmdb_problems_become_clear_errors(
    signed_in: httpx.AsyncClient, api_app: fastapi.FastAPI, fake_tmdb: FakeTMDB
) -> None:
    missing = await signed_in.get(f"/api/movies/{MAX_ID + 1}")
    api_app.dependency_overrides[get_tmdb_client] = lambda: make_tmdb_client(fake_tmdb, api_key=None)
    unconfigured = await signed_in.get("/api/search", params={"query": "x"})

    assert missing.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert unconfigured.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE
    assert "MINTRACK__TMDB__API_KEY" in unconfigured.json()["detail"]


async def test_a_movie_page_shows_the_users_tracking(signed_in: httpx.AsyncClient) -> None:
    movie_id = media_id("movie", "Paper Moons")
    await signed_in.get(f"/api/movies/{movie_id}")
    await signed_in.put(f"/api/movies/{movie_id}/tracking", json={"watched": True})

    movie = (await signed_in.get(f"/api/movies/{movie_id}")).json()

    assert movie["tracking"]["status"] == "watched"
    assert movie["tracking"]["watched_at"] is not None
