import datetime as dt

import httpx
import pytest

from mintrack.config import get_config
from mintrack.integrations.tvmaze import client as tvmaze
from tests.fakes.tvmaze import TVMAZE_URL, FakeTvmaze, tvmaze_episode


async def test_lookup_follows_the_redirect_to_the_show() -> None:
    fake = FakeTvmaze(shows={81189: (169, [])})

    assert await fake.client().lookup_show(81189) == 169
    assert fake.requests == ["/lookup/shows?thetvdb=81189", "/shows/169"]


async def test_lookup_of_an_unknown_show_finds_nothing() -> None:
    assert await FakeTvmaze().client().lookup_show(1) is None


async def test_episodes_keep_the_airstamp_only_when_the_time_is_known() -> None:
    date_only: dict[str, object] = {"season": 1, "number": 3, "airtime": "", "airstamp": "2026-12-04T12:00:00+00:00"}
    fake = FakeTvmaze(
        shows={1: (10, [tvmaze_episode(1, 1, "2026-11-20T02:00:00+00:00"), tvmaze_episode(1, 2, None), date_only])}
    )

    episodes = await fake.client().episodes(10)

    assert [(episode.number, episode.exact_airstamp) for episode in episodes] == [
        (1, dt.datetime(2026, 11, 20, 2, tzinfo=dt.UTC)),
        (2, None),
        (3, None),
    ]


async def test_rate_limited_calls_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tvmaze, "RATE_LIMIT_WAIT_SECONDS", 0)
    answers = iter([httpx.Response(429), httpx.Response(429), httpx.Response(200, json=[])])
    transport = httpx.MockTransport(lambda _: next(answers))
    client = tvmaze.TvmazeClient(httpx.AsyncClient(transport=transport, base_url=TVMAZE_URL))

    assert await client.episodes(10) == []


async def test_rate_limit_gives_up_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tvmaze, "RATE_LIMIT_WAIT_SECONDS", 0)
    transport = httpx.MockTransport(lambda _: httpx.Response(429))
    client = tvmaze.TvmazeClient(httpx.AsyncClient(transport=transport, base_url=TVMAZE_URL))

    with pytest.raises(httpx.HTTPStatusError):
        await client.episodes(10)


async def test_the_client_calls_the_configured_address_as_mintrack_and_follows_the_lookup_redirect(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("MINTRACK__TVMAZE__URL", "http://tvmaze.test")
    fake = FakeTvmaze(shows={81189: (169, [tvmaze_episode(1, 1, "2026-11-20T02:00:00+00:00")])})

    async with tvmaze.tvmaze_client(fake.transport()) as client:
        tvmaze_id = await client.lookup_show(81189)
        episodes = await client.episodes(169)

    assert (tvmaze_id, len(episodes)) == (169, 1)
    assert fake.requests == ["/lookup/shows?thetvdb=81189", "/shows/169", "/shows/169/episodes"]
    assert fake.hosts == {"tvmaze.test"}
    assert fake.user_agents == {f"MinTrack/{get_config().project.version}"}
