import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.config import get_config
from mintrack.db.models import JellyfinAccount, User


async def test_the_token_is_stored_encrypted_and_reads_as_none_under_another_secret_key(
    db_session: AsyncSession, user: User, secret_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = JellyfinAccount(
        user_id=user.id, server_url="http://jf", server_id="s", jellyfin_user_id="u", username="bob", token="t0ken"
    )
    db_session.add(account)
    await db_session.commit()

    stored = await db_session.scalar(sa.text("SELECT token FROM jellyfin_accounts WHERE id = :id"), {"id": account.id})
    assert stored is not None
    assert "t0ken" not in stored
    await db_session.refresh(account)
    assert account.token == "t0ken"

    monkeypatch.setenv("MINTRACK__SECURITY__SECRET_KEY", "another-secret-key-of-at-least-32-characters")
    get_config.cache_clear()
    await db_session.refresh(account)
    assert account.token is None
