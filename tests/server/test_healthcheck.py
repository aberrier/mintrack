import time

import fastapi
import httpx
import pytest
from sqlalchemy.engine import URL

from mintrack.db.database import DatabaseManager, get_database

DEGRADED = {"status": "degraded", "database": "unavailable"}


def unreachable_database(host: str, port: int) -> DatabaseManager:
    return DatabaseManager(
        URL.create("postgresql+psycopg", username="u", password="p", host=host, port=port, database="d")
    )


async def test_healthy_when_the_database_answers(database: DatabaseManager, client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_degraded_when_the_database_refuses_connections(app: fastapi.FastAPI, client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_database] = lambda: unreachable_database("127.0.0.1", 1)

    response = await client.get("/api/health")

    assert response.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == DEGRADED


@pytest.mark.allow_hosts(["10.255.255.1"])
async def test_degraded_within_three_seconds_when_the_database_never_answers(
    app: fastapi.FastAPI, client: httpx.AsyncClient
) -> None:
    # A non-routable address: the connection attempt hangs instead of failing.
    app.dependency_overrides[get_database] = lambda: unreachable_database("10.255.255.1", 5432)

    started = time.monotonic()
    response = await client.get("/api/health")

    assert time.monotonic() - started < 3
    assert response.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == DEGRADED
