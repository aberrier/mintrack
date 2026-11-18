"""user time zones postgresql knows

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 09:00:00.000000+00:00

"""

import collections.abc
import importlib.resources

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | collections.abc.Sequence[str] | None = "0009"
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None


def _links() -> dict[str, str]:
    """Each legacy zone name of the tz database and the zone it stands for."""
    source = importlib.resources.files("tzdata.zoneinfo").joinpath("tzdata.zi").read_text(encoding="utf-8")
    return {name: target for _, target, name in (line.split() for line in source.splitlines() if line[:2] == "L ")}


def upgrade() -> None:
    # Legacy names (Asia/Calcutta...) were accepted, though PostgreSQL may not know them: their current name, or UTC.
    connection = op.get_bind()
    known = set(connection.scalars(sa.text("SELECT name FROM pg_timezone_names")))
    stored = set(connection.scalars(sa.text("SELECT DISTINCT timezone FROM users")))
    links = _links()
    for name in stored - known:
        target, seen = name, {name}
        while (target := links.get(target, target)) not in seen:
            seen.add(target)
        connection.execute(
            sa.text("UPDATE users SET timezone = :new WHERE timezone = :old"),
            {"new": target if target in known else "UTC", "old": name},
        )


def downgrade() -> None:
    pass
