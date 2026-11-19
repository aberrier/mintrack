import datetime as dt

import fastapi

from mintrack.core.stats.managers import Statistics, StatsManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(tags=["stats"])


@router.get("/stats")
async def stats(user: CurrentUserDepType, session: DbSessionDepType) -> Statistics:
    """The user's own statistics: totals, time spent, watches per month, streaks of days in their time zone, and top
    genres and networks."""
    return await StatsManager(session).statistics(user, dt.datetime.now(dt.UTC))
