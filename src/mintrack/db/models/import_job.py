import datetime as dt
import enum
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mintrack.db.base import DatabaseModel

from .media import text_enum


class ImportSource(enum.StrEnum):
    YAMTRACK = enum.auto()
    TVTIME = enum.auto()


class ImportStatus(enum.StrEnum):
    PENDING = enum.auto()
    RUNNING = enum.auto()
    DONE = enum.auto()
    FAILED = enum.auto()


class UnmatchedItem(typing.TypedDict):
    title: str
    reason: str


class ImportReport(typing.TypedDict):
    imported: int
    already_present: int
    unmatched_count: int
    unmatched: list[UnmatchedItem]


class ImportJob(DatabaseModel):
    __tablename__ = "import_jobs"
    __table_args__ = (
        sa.Index(None, "user_id", "created_at"),
        # One pending or running import per user.
        sa.Index(
            "unique_import_jobs_active_user_id",
            "user_id",
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[ImportSource] = mapped_column(text_enum(ImportSource))
    status: Mapped[ImportStatus] = mapped_column(text_enum(ImportStatus), default=ImportStatus.PENDING)
    filename: Mapped[str]
    # The uploaded file, kept only until the job ends.
    file: Mapped[bytes | None] = mapped_column(sa.LargeBinary, deferred=True)
    total: Mapped[int] = mapped_column(default=0)
    processed: Mapped[int] = mapped_column(default=0)
    report: Mapped[ImportReport | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=sa.func.now())
    updated_at: Mapped[dt.datetime]
    finished_at: Mapped[dt.datetime | None]
