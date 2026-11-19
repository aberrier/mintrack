import datetime as dt

import fastapi
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import TrackingStatus
from tests.core.upcoming.factories import add_show, follow, watch
from tests.server.api.conftest import CreateUser, log_in


async def test_stats_give_the_users_own_figures(
    api: httpx.AsyncClient, create_user: CreateUser, db_session: AsyncSession
) -> None:
    alice = await create_user()
    await log_in(api)
    show, episodes = await add_show(db_session, {(1, 1): None, (1, 2): None}, title="Dark")
    show.network, show.genres = "Netflix", ["Drama"]
    episodes[1, 1].runtime = episodes[1, 2].runtime = 50
    await follow(db_session, alice, show, TrackingStatus.FINISHED)
    for episode in episodes.values():
        await watch(db_session, alice, episode, dt.datetime.now(dt.UTC))

    response = await api.get("/api/stats")

    assert response.status_code == fastapi.status.HTTP_200_OK
    stats = response.json()
    assert (stats["episodes"], stats["episode_minutes"], stats["shows"], stats["finished_shows"]) == (2, 100, 1, 1)
    assert (stats["current_streak"], stats["longest_streak"]) == (1, 1)
    assert (stats["months"][-1]["episodes"], len(stats["months"])) == (2, 12)
    assert stats["genres"] == [{"name": "Drama", "titles": 1}]
    assert stats["networks"] == [{"name": "Netflix", "titles": 1}]
