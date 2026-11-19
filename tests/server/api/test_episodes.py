import datetime as dt
import uuid

import fastapi
import httpx

from tests.server.api.test_tracking import episode_id, show_page


async def test_an_episode_sheet_has_its_show_texts_tmdb_score_and_the_users_watch_and_rating(
    signed_in: httpx.AsyncClient,
) -> None:
    tmdb_id, show = await show_page(signed_in, "Sheet Show")
    second = episode_id(show, 1, 2)
    await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [second], "watched": True})
    await signed_in.put(f"/api/episodes/{second}/rating", json={"stars": 4, "review": "Tense."})

    sheet = (await signed_in.get(f"/api/episodes/{second}")).json()
    unwatched = (await signed_in.get(f"/api/episodes/{episode_id(show, 1, 3)}")).json()

    assert sheet["watched_at"] is not None
    assert sheet["rating"]["stars"] == 4
    assert {key: sheet[key] for key in ("tmdb_id", "show_title", "network", "season_number", "episode_number")} == {
        "tmdb_id": tmdb_id,
        "show_title": "Sheet Show",
        "network": "Channel Nine",
        "season_number": 1,
        "episode_number": 2,
    }
    assert (sheet["overview"], sheet["vote_average"], sheet["vote_count"]) == ("What happens in episode 2.", 7.5, 24)
    assert (unwatched["watched_at"], unwatched["rating"]) == (None, None)


async def test_an_unknown_episode_is_not_found(signed_in: httpx.AsyncClient) -> None:
    response = await signed_in.get(f"/api/episodes/{uuid.uuid7()}")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND


async def test_a_watch_can_be_dated_in_the_past_but_not_in_the_future(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, show = await show_page(signed_in, "Dated Show")
    first = episode_id(show, 1, 1)
    await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [first], "watched": True})
    past = dt.datetime(2025, 3, 14, 20, 30, tzinfo=dt.UTC)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)

    dated = await signed_in.put(f"/api/episodes/{first}/watched", json={"watched_at": past.isoformat()})
    refused = await signed_in.put(f"/api/episodes/{first}/watched", json={"watched_at": future.isoformat()})
    sheet = (await signed_in.get(f"/api/episodes/{first}")).json()

    assert dated.status_code == fastapi.status.HTTP_200_OK
    assert dt.datetime.fromisoformat(dated.json()["watched"][first]) == past
    assert refused.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
    assert dt.datetime.fromisoformat(sheet["watched_at"]) == past


async def test_an_episode_not_watched_has_no_date_to_change(signed_in: httpx.AsyncClient) -> None:
    _, show = await show_page(signed_in, "Undated Watch Show")

    response = await signed_in.put(
        f"/api/episodes/{episode_id(show, 1, 1)}/watched", json={"watched_at": "2025-01-01T00:00:00Z"}
    )

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
