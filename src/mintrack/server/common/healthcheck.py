import asyncio
import enum

import fastapi
import pydantic
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from mintrack.db.dependencies import DatabaseDepType
from mintrack.observability.logging import logger

# Upper bound for the database check, so the endpoint answers even when PostgreSQL hangs.
DATABASE_CHECK_TIMEOUT_SECONDS = 2

router = fastapi.APIRouter(prefix="/health", tags=["health"])


class HealthStatus(enum.StrEnum):
    OK = enum.auto()
    DEGRADED = enum.auto()


class DatabaseStatus(enum.StrEnum):
    OK = enum.auto()
    UNAVAILABLE = enum.auto()


class HealthResponse(pydantic.BaseModel):
    """Public, unauthenticated: never add versions or error details here."""

    status: HealthStatus
    database: DatabaseStatus


@router.get(
    "",
    responses={fastapi.status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(response: fastapi.Response, database: DatabaseDepType) -> HealthResponse:
    try:
        async with asyncio.timeout(DATABASE_CHECK_TIMEOUT_SECONDS), database.engine.connect() as connection:
            await connection.execute(sa.text("SELECT 1"))
    except (TimeoutError, OSError, SQLAlchemyError) as error:
        logger.warning("health check: database unavailable", error=type(error).__name__)
        response.status_code = fastapi.status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status=HealthStatus.DEGRADED, database=DatabaseStatus.UNAVAILABLE)
    return HealthResponse(status=HealthStatus.OK, database=DatabaseStatus.OK)
