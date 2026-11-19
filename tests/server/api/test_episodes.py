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


async def test_a_watch_is_dated_from_the_day_before_the_episode_aired_to_now(signed_in: httpx.AsyncClient) -> None:
    tmdb_id, show = await show_page(signed_in, "Dated Show")
    first = episode_id(show, 1, 1)
    await signed_in.post(f"/api/shows/{tmdb_id}/watched", json={"episode_ids": [first], "watched": True})
    season = next(season for season in show["seasons"] if season["season_number"] == 1)
    aired = dt.date.fromisoformat(season["episodes"][0]["air_date"])
    earliest = dt.datetime.combine(aired - dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)

    dated = await signed_in.put(f"/api/episodes/{first}/watched", json={"watched_at": earliest.isoformat()})
    refused = [
        await signed_in.put(f"/api/episodes/{first}/watched", json={"watched_at": at.isoformat()})
        for at in (future, earliest - dt.timedelta(minutes=1))
    ]
    sheet = (await signed_in.get(f"/api/episodes/{first}")).json()

    assert dated.status_code == fastapi.status.HTTP_200_OK
    assert dt.datetime.fromisoformat(dated.json()["watched"][first]) == earliest
    assert [response.status_code for response in refused] == [fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT] * 2
    assert dt.datetime.fromisoformat(sheet["watched_at"]) == earliest


async def test_an_episode_not_watched_has_no_date_to_change(signed_in: httpx.AsyncClient) -> None:
    _, show = await show_page(signed_in, "Undated Watch Show")

    response = await signed_in.put(
        f"/api/episodes/{episode_id(show, 1, 1)}/watched", json={"watched_at": dt.datetime.now(dt.UTC).isoformat()}
    )

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
