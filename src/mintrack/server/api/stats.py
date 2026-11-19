import datetime as dt

import fastapi
import pydantic

from mintrack.core.stats.managers import StatsManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(tags=["stats"])


class MonthResponse(pydantic.BaseModel):
    # The first day of the month, in the user's time zone.
    month: dt.date
    episodes: int
    movies: int


class RankedResponse(pydantic.BaseModel):
    name: str
    # Shows with a watched episode, and watched movies.
    titles: int


class StatsResponse(pydantic.BaseModel):
    episodes: int
    movies: int
    shows: int
    finished_shows: int
    episode_minutes: int
    movie_minutes: int
    # Left out of the minutes: TMDB gives no runtime for the movie, nor for any episode of the show.
    episodes_without_runtime: int
    movies_without_runtime: int
    # The last 12 months, oldest first.
    months: list[MonthResponse]
    current_streak: int
    longest_streak: int
    genres: list[RankedResponse]
    networks: list[RankedResponse]


@router.get("/stats")
async def stats(user: CurrentUserDepType, session: DbSessionDepType) -> StatsResponse:
    """The user's own statistics: totals, time spent, watches per month, streaks of days in their time zone, and top
    genres and networks."""
    statistics = await StatsManager(session).statistics(user, dt.datetime.now(dt.UTC))
    return StatsResponse.model_validate(statistics, from_attributes=True)
