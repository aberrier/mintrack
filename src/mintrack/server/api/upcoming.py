import datetime as dt
import uuid

import fastapi
import pydantic

from mintrack.core.upcoming.managers import UpcomingManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(tags=["upcoming"])


class UpcomingEpisode(pydantic.BaseModel):
    episode_id: uuid.UUID
    tmdb_id: int
    show_title: str
    poster_path: str | None
    season_number: int
    episode_number: int
    title: str
    airstamp: dt.datetime | None
    day: dt.date | None


class UpcomingDay(pydantic.BaseModel):
    day: dt.date
    episodes: list[UpcomingEpisode]


class UpcomingResponse(pydantic.BaseModel):
    # The user's time zone, in which days are grouped and air times are shown.
    time_zone: str
    new: list[UpcomingEpisode]
    days: list[UpcomingDay]


class UpNextResponse(pydantic.BaseModel):
    episodes: list[UpcomingEpisode]


@router.get("/upcoming")
async def upcoming(user: CurrentUserDepType, session: DbSessionDepType) -> UpcomingResponse:
    result = await UpcomingManager(session).upcoming(user, now=dt.datetime.now(dt.UTC))
    return UpcomingResponse.model_validate(
        {"time_zone": user.timezone, "new": result.new, "days": result.days}, from_attributes=True
    )


@router.get("/up-next")
async def up_next(user: CurrentUserDepType, session: DbSessionDepType) -> UpNextResponse:
    episodes = await UpcomingManager(session).up_next(user, now=dt.datetime.now(dt.UTC))
    return UpNextResponse.model_validate({"episodes": episodes}, from_attributes=True)
