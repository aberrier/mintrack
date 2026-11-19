"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-19 00:20:01.835565+00:00

"""

import collections.abc
import pathlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | collections.abc.Sequence[str] | None = None
branch_labels: str | collections.abc.Sequence[str] | None = None
depends_on: str | collections.abc.Sequence[str] | None = None

PROCRASTINATE_SCHEMA = pathlib.Path(__file__).parent.parent / "procrastinate" / "schema-3.11.0.sql"

DROP_PROCRASTINATE = r"""
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = current_schema()
            AND tablename LIKE 'procrastinate\_%' LOOP
        EXECUTE format('DROP TABLE %I CASCADE', item.tablename);
    END LOOP;
    FOR item IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = current_schema() AND p.proname LIKE 'procrastinate\_%' LOOP
        EXECUTE format('DROP ROUTINE %s CASCADE', item.signature);
    END LOOP;
    FOR item IN SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = current_schema() AND t.typname LIKE 'procrastinate\_%' AND t.typtype IN ('e', 'c') LOOP
        EXECUTE format('DROP TYPE %I CASCADE', item.typname);
    END LOOP;
END;
$$;
"""


def execute_script(sql: str) -> None:
    # A DBAPI cursor without parameters: the SQL holds colons and percent signs that parameter styles would misread.
    op.get_bind().connection.cursor().execute(sql)


def upgrade() -> None:
    # Procrastinate's tables, types and functions, from its own SQL.
    execute_script(PROCRASTINATE_SCHEMA.read_text(encoding="utf-8"))
    op.create_table(
        "login_failures",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("address", sa.TEXT(), nullable=False),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_failures")),
    )
    op.create_index(
        op.f("index_login_failures_on_address_failed_at"), "login_failures", ["address", "failed_at"], unique=False
    )
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("movie", "tv", name="mediatype", native_enum=False, create_constraint=True, length=None),
            nullable=False,
        ),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.Column("overview", sa.TEXT(), nullable=False),
        sa.Column("poster_path", sa.TEXT(), nullable=True),
        sa.Column("backdrop_path", sa.TEXT(), nullable=True),
        sa.Column("network", sa.TEXT(), nullable=True),
        sa.Column("runtime", sa.Integer(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("tmdb_status", sa.TEXT(), nullable=True),
        sa.Column("tvdb_id", sa.Integer(), nullable=True),
        sa.Column("tvmaze_id", sa.Integer(), nullable=True),
        sa.Column("refreshed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("media_type", "tmdb_id", name=op.f("unique_media_media_type_tmdb_id")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("password_hash", sa.TEXT(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.TEXT(), server_default="UTC", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("link_token_hash", sa.LargeBinary(), nullable=True),
        sa.Column("link_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("link_token_hash", name=op.f("unique_users_link_token_hash")),
    )
    op.create_index("unique_users_lower_username", "users", [sa.literal_column("lower(username)")], unique=True)
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("unique_api_tokens_token_hash")),
    )
    op.create_index(op.f("index_api_tokens_on_user_id"), "api_tokens", ["user_id"], unique=False)
    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("airstamp", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_episodes_media_id_media"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_episodes")),
        sa.UniqueConstraint(
            "media_id",
            "season_number",
            "episode_number",
            name=op.f("unique_episodes_media_id_season_number_episode_number"),
        ),
    )
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("yamtrack", "tvtime", name="importsource", native_enum=False, create_constraint=True, length=None),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "failed",
                name="importstatus",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.TEXT(), nullable=False),
        sa.Column("file", sa.LargeBinary(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_import_jobs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
    )
    op.create_index(
        op.f("index_import_jobs_on_user_id_created_at"), "import_jobs", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        "unique_import_jobs_active_user_id",
        "import_jobs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_table(
        "jellyfin_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("server_url", sa.TEXT(), nullable=False),
        sa.Column("server_id", sa.TEXT(), nullable=False),
        sa.Column("jellyfin_user_id", sa.TEXT(), nullable=False),
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("token", sa.TEXT(), nullable=False),
        sa.Column("synced_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "last_sync_status",
            sa.Enum(
                "ok",
                "unreachable",
                "unauthorized",
                "failed",
                name="jellyfinsyncstatus",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("last_sync_imported", sa.Integer(), nullable=False),
        sa.Column("last_sync_skipped", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_jellyfin_accounts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jellyfin_accounts")),
        sa.UniqueConstraint(
            "user_id",
            "server_id",
            "jellyfin_user_id",
            name=op.f("unique_jellyfin_accounts_user_id_server_id_jellyfin_user_id"),
        ),
    )
    op.create_table(
        "seasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], name=op.f("fk_seasons_media_id_media"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint("media_id", "season_number", name=op.f("unique_seasons_media_id_season_number")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("user_agent", sa.TEXT(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("unique_sessions_token_hash")),
    )
    op.create_index(op.f("index_sessions_on_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "user_media",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "watch_later",
                "watching",
                "up_to_date",
                "finished",
                "stopped",
                "watched",
                "not_started",
                name="trackingstatus",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_user_media_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_media_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_user_media")),
    )
    op.create_index(op.f("index_user_media_on_media_id"), "user_media", ["media_id"], unique=False)
    op.create_table(
        "watched_movies",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("watched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_watched_movies_media_id_media"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_watched_movies_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "media_id", name=op.f("pk_watched_movies")),
    )
    op.create_index(
        op.f("index_watched_movies_on_user_id_watched_at_media_id"),
        "watched_movies",
        ["user_id", "watched_at", "media_id"],
        unique=False,
    )
    op.create_table(
        "episode_notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["episodes.id"],
            name=op.f("fk_episode_notifications_episode_id_episodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_episode_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "episode_id", name=op.f("pk_episode_notifications")),
    )
    op.create_index(
        op.f("index_episode_notifications_on_episode_id"), "episode_notifications", ["episode_id"], unique=False
    )
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint", sa.TEXT(), nullable=False),
        sa.Column("p256dh", sa.TEXT(), nullable=False),
        sa.Column("auth", sa.TEXT(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_push_subscriptions_session_id_sessions"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_push_subscriptions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("unique_push_subscriptions_endpoint")),
    )
    op.create_index(op.f("index_push_subscriptions_on_session_id"), "push_subscriptions", ["session_id"], unique=False)
    op.create_index(op.f("index_push_subscriptions_on_user_id"), "push_subscriptions", ["user_id"], unique=False)
    op.create_table(
        "watched_episodes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("watched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["episodes.id"], name=op.f("fk_watched_episodes_episode_id_episodes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_watched_episodes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "episode_id", name=op.f("pk_watched_episodes")),
    )
    op.create_index(op.f("index_watched_episodes_on_episode_id"), "watched_episodes", ["episode_id"], unique=False)
    op.create_index(
        op.f("index_watched_episodes_on_user_id_watched_at_episode_id"),
        "watched_episodes",
        ["user_id", "watched_at", "episode_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("index_watched_episodes_on_user_id_watched_at_episode_id"), table_name="watched_episodes")
    op.drop_index(op.f("index_watched_episodes_on_episode_id"), table_name="watched_episodes")
    op.drop_table("watched_episodes")
    op.drop_index(op.f("index_push_subscriptions_on_user_id"), table_name="push_subscriptions")
    op.drop_index(op.f("index_push_subscriptions_on_session_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    op.drop_index(op.f("index_episode_notifications_on_episode_id"), table_name="episode_notifications")
    op.drop_table("episode_notifications")
    op.drop_index(op.f("index_watched_movies_on_user_id_watched_at_media_id"), table_name="watched_movies")
    op.drop_table("watched_movies")
    op.drop_index(op.f("index_user_media_on_media_id"), table_name="user_media")
    op.drop_table("user_media")
    op.drop_index(op.f("index_sessions_on_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("seasons")
    op.drop_table("jellyfin_accounts")
    op.drop_index(
        "unique_import_jobs_active_user_id",
        table_name="import_jobs",
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index(op.f("index_import_jobs_on_user_id_created_at"), table_name="import_jobs")
    op.drop_table("import_jobs")
    op.drop_table("episodes")
    op.drop_index(op.f("index_api_tokens_on_user_id"), table_name="api_tokens")
    op.drop_table("api_tokens")
    op.drop_index("unique_users_lower_username", table_name="users")
    op.drop_table("users")
    op.drop_table("media")
    op.drop_index(op.f("index_login_failures_on_address_failed_at"), table_name="login_failures")
    op.drop_table("login_failures")
    execute_script(DROP_PROCRASTINATE)
