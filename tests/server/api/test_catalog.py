import datetime as dt

import fastapi
import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Media, MediaType
from mintrack.integrations.tmdb.client import get_tmdb_client
from tests.conftest import make_tmdb_client
from tests.fakes.tmdb import MAX_ID, TRENDING, FakeTMDB, media_id


async def test_search_finds_only_the_chosen_type_with_the_users_status(signed_in: httpx.AsyncClient) -> None:
    show_id = media_id("tv", "Orbit Kitchen")
    await signed_in.get(f"/api/shows/{show_id}")
    await signed_in.put(f"/api/shows/{show_id}/tracking", json={"status": "watching"})

    shows = await signed_in.get("/api/search", params={"query": "Orbit Kitchen", "type": "tv"})
    movies = await signed_in.get("/api/search", params={"query": "Orbit Kitchen", "type": "movie"})

    assert shows.status_code == movies.status_code == fastapi.status.HTTP_200_OK
    assert [(r["media_type"], r["year"], r["tracking_status"]) for r in shows.json()] == [("tv", 2024, "not_started")]
    assert [(r["media_type"], r["year"], r["tracking_status"]) for r in movies.json()] == [("movie", None, None)]


async def test_trending_lists_the_weeks_shows_or_movies_with_the_users_status(signed_in: httpx.AsyncClient) -> None:
    tracked = media_id("movie", TRENDING[1])
    await signed_in.get(f"/api/movies/{tracked}")
    await signed_in.put(f"/api/movies/{tracked}/tracking", json={"watched": True})

    shows = await signed_in.get("/api/discover/trending", params={"type": "tv"})
    movies = await signed_in.get("/api/discover/trending", params={"type": "movie"})

    assert shows.status_code == movies.status_code == fastapi.status.HTTP_200_OK
    assert [(r["media_type"], r["title"], r["tracking_status"]) for r in shows.json()] == [
        ("tv", title, None) for title in TRENDING
    ]
    assert [(r["tmdb_id"], r["tracking_status"]) for r in movies.json()] == [
        (media_id("movie", TRENDING[0]), None),
        (tracked, "watched"),
    ]


async def test_show_and_movie_pages_carry_the_backdrop_network_and_runtime(signed_in: httpx.AsyncClient) -> None:
    show_id, movie_id = media_id("tv", "Backdrop Show"), media_id("movie", "Backdrop Movie")

    show = (await signed_in.get(f"/api/shows/{show_id}")).json()
    movie = (await signed_in.get(f"/api/movies/{movie_id}")).json()

    assert (show["backdrop_path"], show["network"], show["runtime"]) == (
        f"/backdrop-{show_id}.jpg",
        "Channel Nine",
        None,
    )
    assert (movie["backdrop_path"], movie["network"], movie["runtime"]) == (f"/backdrop-{movie_id}.jpg", None, 118)


async def test_a_show_page_lists_seasons_with_specials_last(signed_in: httpx.AsyncClient) -> None:
    await signed_in.get("/api/search", params={"query": "Night Shift"})

    response = await signed_in.get(f"/api/shows/{media_id('tv', 'Night Shift')}")

    show = response.json()
    assert response.status_code == fastapi.status.HTTP_200_OK
    assert (show["title"], show["tracking"]) == ("Night Shift", None)
    # S02E03 airs in a week.
    assert [
        (s["season_number"], s["episode_count"], s["watched_count"], s["aired_count"]) for s in show["seasons"]
    ] == [(1, 3, 0, 3), (2, 3, 0, 2), (0, 1, 0, 1)]
    assert all("episodes" not in season for season in show["seasons"])


async def test_a_season_lists_its_episodes_in_order(signed_in: httpx.AsyncClient) -> None:
    show_id = media_id("tv", "Night Shift")
    await signed_in.get(f"/api/shows/{show_id}")

    season = await signed_in.get(f"/api/shows/{show_id}/seasons/2")
    missing = await signed_in.get(f"/api/shows/{show_id}/seasons/9")
    never_loaded = await signed_in.get(f"/api/shows/{media_id('tv', 'Never Opened')}/seasons/1")

    assert season.status_code == fastapi.status.HTTP_200_OK
    body = season.json()
    assert body["season_number"] == 2
    assert [(e["season_number"], e["episode_number"]) for e in body["episodes"]] == [(2, 1), (2, 2), (2, 3)]
    assert set(body["episodes"][0]) == {"id", "season_number", "episode_number", "title", "air_date", "airstamp"}
    assert missing.status_code == never_loaded.status_code == fastapi.status.HTTP_404_NOT_FOUND


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
