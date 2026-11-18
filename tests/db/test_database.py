import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def test_app_connections_cancel_long_statements_and_skip_jit(db_session: AsyncSession) -> None:
    assert await db_session.scalar(sa.text("SHOW statement_timeout")) == "30s"
    assert await db_session.scalar(sa.text("SHOW jit")) == "off"
