# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What MinTrack is

A minimal, self-hosted TV and movie tracker with the TV Time experience: FastAPI + SQLAlchemy 2 (async) + Alembic on
PostgreSQL, an Angular app in `frontend/` served by the backend, one Docker image. See `README.md` for the scope.

## References

- **Features, security and behaviour** follow Yamtrack (`../yamtrack`) and its fork Floppy (`../floppy`): keep their
  proven choices, and state in the plan or PR why when diverging.
- **Tooling, code structure and tests** follow the maintainer's reference FastAPI project. Its gaps or out-of-scope shortcuts are not
  inherited (its CORS, Sentry and auth settings, for example).
- **Frontend conventions** follow the maintainer's reference Angular project, except that it is a
  desktop app and MinTrack is phone-first (see Frontend below).
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
just dev        # mintrack server --reload, configured by .env (copy .env.example, which is for development only)
just dev-frontend  # ng serve on :4200, proxying /api to just dev
just image      # build the Docker image as ghcr.io/aberrier/mintrack:edge
```

To run the built image with `docker-compose.yml`, put the image `ghcr.io/aberrier/mintrack:edge` and the values to
edit in a `docker-compose.override.yml` (gitignored), as the CI's browser-test job does.

Always run Python tools through `uv run`. Run `just` (check and test) before committing. Install just with
`uv tool install rust-just`.

## Layout

```
src/mintrack/
  __main__.py      # config errors -> readable message; logging, Sentry, CLI
  cli/commands/    # one Typer app per module, registered in cli/app.py: mintrack server | worker | db | healthcheck | users | import
  config/          # Config(BaseSettings): MINTRACK__SECTION__FIELD variables, *_FILE variants, .env
  core/<domain>/   # business logic: accounts (users, sessions, password links, login limit), api_tokens, catalog (TMDB cache),
                   # imports (Yamtrack, TV Time), jellyfin (sync), push, ratings (a user's stars and reviews), stats (a user's figures),
                   # tracking (watched episodes, statuses), upcoming (watch list, air times)
  db/              # DatabaseModel, models/, DatabaseManager, Alembic config built in code, migrations/
  integrations/    # clients of outside services: tmdb/, tvmaze/ (air times), jellyfin/
  observability/   # structlog logging, Sentry (off unless a DSN is set, no personal data)
  server/          # build_app(): /api router (public and session-protected), middlewares
  server/mcp/      # MCP server at /mcp, outside /api: users' API tokens as Bearer tokens, tools that call the managers
  worker/          # Procrastinate: get_worker_app(), tasks on the Blueprint of tasks.py; its own compose service, or inside the server
tests/             # mirrors src/; conftest.py holds the opt-in database fixtures; fakes/ fakes outside services
frontend/src/app/
  core/api/        # ApiService: one group of endpoints per domain, relative /api URLs
  core/auth/       # AuthStore ($user), signedIn and admin guards, the 401 interceptor
  core/i18n/       # injectTranslator, English only, paths such as app.home.title
  core/icons/      # Material Symbols SVGs registered by name; import only the icons used
  core/tracking/   # TrackingStore (optimistic writes), WatchListStore (a view derived from it) and episode helpers
  core/            # also imports/, jellyfin/, push/, pwa/ (updates), dates.ts, notify.ts (snackbars), title.ts (page titles)
  shell/           # the phone frame: scrolling content and the bottom navigation
  pages/<page>/    # one lazy-loaded standalone component per route (app.routes.ts)
  shared/          # components used by several pages
frontend/src/types/ # global namespaces (Model for API shapes)
frontend/e2e/      # Playwright acceptance suite: specs/ (domain language), dsl/ (actors, fixtures), drivers/ (pages, CLI, API)
Dockerfile, docker-compose.yml  # the image and the install, self-contained; README "Install" repeats docker-compose.yml
.env.example     # development settings for `just dev`
```

Business logic goes in `core/<domain>/managers`, endpoints and their Pydantic schemas in `server/api/`,
dependencies as `*DepType` `Annotated` aliases. Simple endpoints may query SQLAlchemy directly. Lookups several API
modules need (a cached media, an episode and its show) live in `server/api/common.py`, never in another API module.

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
- **Access:** every `/api` route needs a session (and an XSRF header on unsafe methods) unless it is on the public
  router in `server/api/asgi.py`; `tests/server/api/test_access.py` checks every route of the schema. Admin routers
  depend on `get_admin_user`. Endpoints take the request's session with `DbSessionDepType` and commit explicitly.
  `/mcp` is outside `/api` and the schema: it takes a user's API token as Bearer token, never the session cookie, and
  `tests/server/mcp/test_auth.py` checks it.

## Tests

- pytest + pytest-asyncio (auto mode), real PostgreSQL, nothing mocked that we own.
- Database fixtures are opt-in: request `database` (a migrated `test_<name>` database for the session) or
  `db_session` (rolled back after the test). Other tests run without PostgreSQL.
- Sockets are disabled except to localhost; mark a test `@pytest.mark.allow_hosts([...])` when it must reach another
  address.
- ASGI tests use `https://mintrack.test`, the test `public_url`. API tests use the `api` client of
  `tests/server/api/conftest.py`, whose requests run on the test's rolled-back session.

## Frontend

```bash
cd frontend
npm ci
npm run check   # prettier, Angular compiler with strict templates, spec and e2e types
npm test        # Vitest
npm run build   # fails over the bundle budgets (initial: warning at 10 MB, error at 16 MB; component style 8 kB)
npm run e2e     # Playwright against a running server (MINTRACK_E2E_BASE_URL, default http://localhost:8000)
```

`just e2e [playwright args]` starts this worktree's stack (built app, fake TMDB and TVmaze, its own database and port,
state in `.e2e/`) or reuses it, then runs Playwright; `just e2e-stop` stops it. A new worktree hard-links the
`node_modules` of another worktree with the same lockfile. The whole suite takes about a minute on 8 workers (more
workers saturate the server and run slower). While iterating, run `just e2e --project=phone <spec>`,
`just e2e --last-failed` or `just e2e --only-changed`; each run starts with no users, locally a test times out after
20 s, an assertion after 3 s, and the run stops after five failures. Run the whole suite once before handing off, then `just e2e-stop`.

- **Angular:** standalone components, zoneless, `OnPush` everywhere, lazy routes declared in `app.routes.ts` with
  their URL builders in `appRoutes` (`app.paths.ts`, which imports nothing). Signals for state, RxJS for
  asynchronous flows, `toSignal` / `toObservable` at the boundary. No NgRx.
- **State, so one tap feels instant:** each domain gets a store service holding private writable signals and exposing
  read-only ones. A tap updates the store first, then queues the API call. Writes to the same item are serialised
  (`concatMap`), with errors caught inside each queued call so one failure never stops the queue. Each success
  records the server's answer as the item's confirmed value; on error, and only when no later write for that item is
  still queued, the store goes back to the confirmed value and a snackbar says so. A store that only shows a view of
  another store's items (the watch list over the shows) changes its view at once, writes through the owning store
  (which says when it fails) and loads the view again from the server after a failure. Snackbars go through
  `injectNotify()`: messages leave after a few seconds, one with an action after 10 seconds or on navigation.
- **Phone first:** test in the Playwright `phone` project first. Tap targets are at least 48px; content stays inside
  `env(safe-area-inset-*)`; no horizontal scroll. Only the shell's content area scrolls (`100dvh` shell, marked
  `cdkScrollable` for Material overlays), so the router's window scrolling does nothing: the first page with a list
  saves and restores that element's scroll position per history entry.
- **UI:** Material 3 for dialogs, snackbars, menus, form fields and ripples; custom components for the core lists
  (bottom navigation, episode rows, poster cards). Import Material components one by one, never whole modules at the
  root. Tailwind for layout and Material's colour tokens (`bg-surface`, `text-on-surface-variant`); typography from
  Material's type tokens (`[font:var(--mat-sys-headline-small)]`). The theme follows the system (light or dark).
- **No external resources:** no CDN, no Google Fonts (system font stack), icons bundled as SVG. The CSP blocks them
  anyway, and the browser tests fail on any console error.
- **Texts** go through `injectTranslator('app')`, in `core/i18n/translations/app.en.ts`, bundled with the app so
  nothing pops in after the first paint. Paths are typed (`TranslationPath<'app'>`).
