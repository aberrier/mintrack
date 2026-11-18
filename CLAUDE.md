# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What MinTrack is

A minimal, self-hosted TV and movie tracker with the TV Time experience: FastAPI + SQLAlchemy 2 (async) + Alembic on
PostgreSQL, an Angular app in `frontend/` (from M1's second PR), one Docker image. See `README.md` for the scope.

## References

- **Features, security and behaviour** follow Yamtrack (`../yamtrack`) and its fork Floppy (`../floppy`): keep their
  proven choices, and state in the plan or PR why when diverging.
- **Tooling, code structure and tests** follow the maintainer's reference FastAPI project. Its gaps or out-of-scope shortcuts are not
  inherited (its CORS, Sentry and auth settings, for example).
- MinTrack must be easy to install for anyone with Docker; never size a choice for "a few users".

## Development environment

Development runs in WSL2 (Ubuntu), like CI and the image. Native Windows is not supported: psycopg's async mode needs
a selector event loop and pytest-socket breaks asyncio there.

```bash
just dev-db     # PostgreSQL 18 in Docker on 127.0.0.1:5432 (mintrack/mintrack)
just install    # uv sync --locked
just check      # ruff, ruff format --check, ty
just test       # pytest (needs just dev-db for the database tests)
just format     # apply ruff fixes and formatting
just dev        # mintrack server --reload
```

Always run Python tools through `uv run`. Run `just` (check and test) before committing. Install just with
`uv tool install rust-just`.

## Layout

```
src/mintrack/
  __main__.py      # config errors -> readable message; logging, Sentry, CLI
  cli/commands/    # one Typer app per module, registered in cli/app.py: mintrack server | db | healthcheck
  config/          # Config(BaseSettings): MINTRACK__SECTION__FIELD variables, *_FILE variants, .env
  db/              # DatabaseModel, DatabaseManager, Alembic config built in code, migrations/
  observability/   # structlog logging, Sentry (off unless a DSN is set, no personal data)
  server/          # build_app(): /api router, middlewares (proxy headers, security headers, generic 500)
tests/             # mirrors src/; conftest.py holds the opt-in database fixtures
```

Business logic goes in `core/<domain>/managers` (from M2), endpoints and their Pydantic schemas in `server/api/`,
dependencies as `*DepType` `Annotated` aliases. Simple endpoints may query SQLAlchemy directly.

## Rules

- **Configuration variables are a contract** with self-hosters: never rename one without a migration note. Secrets
  are `SecretStr`; error messages name the variable, never the value.
- **`project.public_url`** is the only source of the scheme and origin for anything absolute (cookies, links, push).
  Proxy headers only give the client address. MinTrack is always served at the root of its origin.
- **Time:** business code takes the current time from Python and passes it to queries; `server_default=now()` only
  for audit columns. PostgreSQL's `now()` is frozen for a whole transaction, and tests run in one.
- **Migrations:** `uv run mintrack db makemigrations "message"`; revisions are numbered `0001`, `0002`... and formatted
  by ruff. The server migrates on start.
- **Typing:** `enum.StrEnum` (with `enum.auto()`) over `typing.Literal` for sets of values; no `typing.Any` where a
  real type exists; no `from __future__ import annotations`.
- **Logs:** never pass secrets or personal data as log values: structlog fields end up in the message Sentry receives.
- **Comments** only for the non-obvious why.
- **No CORS middleware:** the API is only called by the app it serves, from the same origin.

## Tests

- pytest + pytest-asyncio (auto mode), real PostgreSQL, nothing mocked that we own.
- Database fixtures are opt-in: request `database` (a migrated `test_<name>` database for the session) or
  `db_session` (rolled back after the test). Other tests run without PostgreSQL.
- Sockets are disabled except to localhost; mark a test `@pytest.mark.allow_hosts([...])` when it must reach another
  address.
- ASGI tests use `https://mintrack.test`, the test `public_url`.
