import dataclasses
import datetime as dt
import uuid

import fastapi
import pydantic

from mintrack.core.upcoming.managers import UpcomingManager, WatchListSection
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.catalog import EpisodeResponse
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
    # From today on; aired episodes not watched are on the watch list.
    days: list[UpcomingDay]


class WatchListEpisode(UpcomingEpisode):
    # Aired regular episodes after this one that the user has not watched.
    remaining: int
    last_watched_at: dt.datetime | None
    section: WatchListSection
    # The regular episode after this one, across season ends, aired or not; None after the last one.
    following: EpisodeResponse | None


class WatchListResponse(pydantic.BaseModel):
    # By section, then most recently watched, then most recently added.
    episodes: list[WatchListEpisode]


@router.get("/upcoming")
async def upcoming(user: CurrentUserDepType, session: DbSessionDepType) -> UpcomingResponse:
    result = await UpcomingManager(session).upcoming(user, now=dt.datetime.now(dt.UTC))
    return UpcomingResponse.model_validate({"time_zone": user.timezone, "days": result.days}, from_attributes=True)


@router.get("/watch-list")
async def watch_list(user: CurrentUserDepType, session: DbSessionDepType) -> WatchListResponse:
    """The next episode of each show in progress, in the sections `next` (watched lately), `dormant` and
    `not_started` (its first episode), in that order."""
    manager = UpcomingManager(session)
    episodes = await manager.watch_list(user, now=dt.datetime.now(dt.UTC))
    following = await manager.following([episode.episode_id for episode in episodes])
    return WatchListResponse(
        episodes=[
            WatchListEpisode.model_validate(
                {**dataclasses.asdict(episode), "following": following.get(episode.episode_id)}, from_attributes=True
            )
            for episode in episodes
        ]
    )
