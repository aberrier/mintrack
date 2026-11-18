import datetime as dt
import typing

import fastapi
import pytest
import sqlalchemy as sa
from mcp import Client
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.database import DatabaseManager
from mintrack.db.models import UserMedia
from tests.fakes.tmdb import MAX_ID, media_id
from tests.server.mcp.conftest import TokenUser, mcp_client

# The fake TMDB names the show and the movie it finds after the query.
TITLE = "Breaking Bad"
SHOW_ID = media_id("tv", TITLE)
MOVIE_ID = media_id("movie", TITLE)
PILOT: dict[str, object] = {"tmdb_id": SHOW_ID, "season_number": 1, "episode_number": 1}


async def call(client: Client, tool: str, arguments: dict[str, object]) -> dict[str, typing.Any]:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


def days_from_today(days: int) -> str:
    return (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=days)).isoformat()


async def test_the_server_lists_its_tools_with_their_hints(mcp_app: fastapi.FastAPI, token_user: TokenUser) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        listed = {tool.name: tool.annotations for tool in (await client.list_tools()).tools}

    hints = {
        name: (a.read_only_hint, a.destructive_hint, a.open_world_hint) for name, a in listed.items() if a is not None
    }
    assert hints == {
        "search_media": (True, None, True),
        "get_show_progress": (True, None, False),
        "list_upcoming": (True, None, False),
        "list_up_next": (True, None, False),
        "mark_episode_watched": (False, False, False),
        "mark_movie_watched": (False, False, False),
        "set_show_status": (False, False, False),
        "unmark_episode_watched": (False, True, False),
        "unmark_movie_watched": (False, True, False),
    }


async def test_search_then_mark_an_episode_in_the_users_time_zone(
    mcp_app: fastapi.FastAPI, token_user: TokenUser
) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        search = await call(client, "search_media", {"query": TITLE})
        marked = await call(client, "mark_episode_watched", PILOT | {"watched_at": "2026-11-17T21:30:00"})
        progress = await call(client, "get_show_progress", {"tmdb_id": SHOW_ID})

    assert search["result"][0] == {
        "tmdb_id": SHOW_ID,
        "media_type": "tv",
        "title": TITLE,
        "release_date": "2024-01-10",
        "tracking_status": None,
    }
    assert marked == {"title": TITLE, "status": "watching"}
    assert (progress["tmdb_id"], progress["title"], progress["status"]) == (SHOW_ID, TITLE, "watching")
    assert [(e["season_number"], e["episode_number"]) for e in progress["episodes"]] == [
        (0, 1),
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (2, 2),
        (2, 3),
    ]
    # Read in Europe/Paris, UTC+1 in November.
    assert progress["episodes"][1] == {
        "season_number": 1,
        "episode_number": 1,
        "title": "Episode 1",
        "air_date": days_from_today(-30),
        "watched_at": "2026-11-17T20:30:00Z",
    }
    assert sum(e["watched_at"] is not None for e in progress["episodes"]) == 1


async def test_mark_movie_watched_defaults_to_now(mcp_app: fastapi.FastAPI, token_user: TokenUser) -> None:
    before = dt.datetime.now(dt.UTC)
    async with mcp_client(mcp_app, token_user.token) as client:
        await call(client, "search_media", {"query": TITLE})
        result = await call(client, "mark_movie_watched", {"tmdb_id": MOVIE_ID})

    assert (result["title"], result["status"]) == (TITLE, "watched")
    assert before <= dt.datetime.fromisoformat(result["watched_at"]) <= dt.datetime.now(dt.UTC)


@pytest.mark.parametrize(
    ("tool", "arguments", "status"),
    [
        ("unmark_episode_watched", PILOT, "watch_later"),
        ("unmark_movie_watched", {"tmdb_id": MOVIE_ID}, "watch_later"),
        ("set_show_status", {"tmdb_id": SHOW_ID, "status": "stopped"}, "stopped"),
        ("set_show_status", {"tmdb_id": SHOW_ID, "status": "watching"}, "watching"),
    ],
)
async def test_each_write_tool_updates_the_tokens_users_tracking(
    mcp_app: fastapi.FastAPI, token_user: TokenUser, tool: str, arguments: dict[str, object], status: str
) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        await call(client, "mark_episode_watched", PILOT)
        await call(client, "mark_movie_watched", {"tmdb_id": MOVIE_ID})
        result = await call(client, tool, arguments)

    assert result["status"] == status


async def test_upcoming_and_up_next_follow_the_users_progress(mcp_app: fastapi.FastAPI, token_user: TokenUser) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        await call(client, "search_media", {"query": TITLE})
        await call(client, "mark_episode_watched", PILOT)
        upcoming = await call(client, "list_upcoming", {})
        up_next = await call(client, "list_up_next", {})

    def episode(season: int, number: int, day: str) -> dict[str, object]:
        return {
            "tmdb_id": SHOW_ID,
            "show_title": TITLE,
            "season_number": season,
            "episode_number": number,
            "title": f"Episode {number}",
            "airstamp": None,
            "day": day,
        }

    in_a_week = days_from_today(7)
    assert upcoming == {"new": [], "days": [{"day": in_a_week, "episodes": [episode(2, 3, in_a_week)]}]}
    assert up_next == {"result": [episode(1, 2, days_from_today(-29))]}


async def test_another_users_tracking_is_not_shown(
    mcp_app: fastapi.FastAPI, token_user: TokenUser, other_token_user: TokenUser
) -> None:
    async with mcp_client(mcp_app, other_token_user.token) as client:
        await call(client, "mark_episode_watched", PILOT)
    async with mcp_client(mcp_app, token_user.token) as client:
        search = await call(client, "search_media", {"query": TITLE})
        progress = await call(client, "get_show_progress", {"tmdb_id": SHOW_ID})
        up_next = await call(client, "list_up_next", {})

    assert search["result"][0]["tracking_status"] is None
    assert progress["status"] is None
    assert all(e["watched_at"] is None for e in progress["episodes"])
    assert up_next == {"result": []}


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("mark_episode_watched", PILOT | {"season_number": 9}, f"{TITLE} has no episode S09E01"),
        ("mark_movie_watched", {"tmdb_id": MAX_ID + 1}, f"No movie with TMDB id {MAX_ID + 1}"),
        ("set_show_status", {"tmdb_id": MAX_ID + 1, "status": "watching"}, f"No tv with TMDB id {MAX_ID + 1}"),
    ],
)
async def test_unknown_media_or_episodes_are_tool_errors(
    mcp_app: fastapi.FastAPI,
    token_user: TokenUser,
    database: DatabaseManager,
    tool: str,
    arguments: dict[str, object],
    message: str,
) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        await call(client, "search_media", {"query": TITLE})
        result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert message in str(result.content)
    async with AsyncSession(database.engine) as session:
        assert await session.scalar(sa.select(UserMedia).where(UserMedia.user_id == token_user.user.id)) is None


async def test_set_show_status_refuses_derived_statuses(mcp_app: fastapi.FastAPI, token_user: TokenUser) -> None:
    async with mcp_client(mcp_app, token_user.token) as client:
        result = await client.call_tool("set_show_status", {"tmdb_id": SHOW_ID, "status": "finished"})

    assert result.is_error
