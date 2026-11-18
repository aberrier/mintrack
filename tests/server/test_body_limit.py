import collections.abc

import httpx

from mintrack.server.common.body_limit import MAX_BODY_BYTES

LOGIN = "/api/auth/login"


async def test_a_body_announced_over_the_limit_is_refused_unread(client: httpx.AsyncClient) -> None:
    response = await client.post(LOGIN, content=b"x" * (MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {"detail": "The request body is too large."}
    # Answered by the app's middlewares: it carries the security headers.
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_body_streamed_without_length_is_cut_at_the_limit(client: httpx.AsyncClient) -> None:
    async def chunks() -> collections.abc.AsyncIterator[bytes]:
        for _ in range(MAX_BODY_BYTES // 65536 + 2):
            yield b"x" * 65536

    response = await client.post(LOGIN, content=chunks(), headers={"Content-Type": "application/json"})

    assert response.status_code == 413
