import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel


class ApiToken(DatabaseModel):
    """A user's credential for the MCP server; only the SHA-256 of the token is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
    last_used_at: Mapped[dt.datetime | None]
