<p align="center">
  <b>MinTrack: a minimal, self-hosted TV and movie tracker with the TV Time experience.</b><br>
  Track movies, TV shows and anime, mark episodes in one tap, and get notified when new ones air.
</p>

MinTrack is a small media tracker you run on your own server, for yourself and the
people you share it with. It focuses on the things TV Time did well on a phone: knowing which
episode comes next, what airs soon, and marking what you watched without friction.
Your Jellyfin servers fill in your history on their own.

> **Status:** before its first release. Everything below works; expect
> changes until 1.0.

## What it does

- **Movies, TV shows and anime.** Anime are tracked as regular TV shows, with
  metadata from TMDB.
- **One tap to mark an episode watched**, another tap to unmark it. One tap
  marks a whole season. When you skip ahead, MinTrack offers to mark the
  previous episodes too.
- **TV Time statuses.** Not started, watching, up to date, finished, stopped
  and watch later (a show set aside). Most of them follow your progress
  automatically.
- **Watch list and upcoming.** The next episode of every show you watch (the
  first one of a show you have not started), and what airs soon, with real air
  times when available.
- **Push notifications** when a new episode of a show you follow airs, on
  Android and iOS, through an installable web app. No app store needed.
- **Several Jellyfin accounts per user**, even on servers you don't
  administer, linked with Quick Connect: MinTrack never sees your Jellyfin
  password. What you watch there shows up in MinTrack within minutes.
- **Easy to self-host and private.** One docker-compose file, several users
  per instance, invited by the admin. No email, no social features, no tracking.
- **An MCP server** so an AI assistant (Claude Code, Claude Desktop...) can read
  and update your tracking, with a token you create on your profile page.
- **Imports from Yamtrack and TV Time**, from your profile page, with watch
  dates kept. Importing the same file again adds nothing. The file (20 MB at
  most) is deleted once imported.
  - Yamtrack: the CSV export (Settings, Export). Movies, TV shows and anime
    are imported (anime from MyAnimeList or AniList and manual entries are
    matched by title); other media types are listed as not matched.
  - TV Time: the `.zip` of the GDPR data export, or one of its files:
    `tracking-prod-records-v2.csv` (followed shows, watched episodes and
    movies) or `tracking-prod-records.csv` (watched episodes). Shows are
    matched by their TVDB id where the file has it, else by title; movies by
    title and year. Archived shows are imported as stopped, shows saved for
    later as watch later. Only these two files are kept until the import ends;
    the others, `seen_episode_source.csv` (where each episode was watched)
    included, are not read: MinTrack does not record where you watched.

## What it does not do

No social network, no recommendations, no ratings or reviews, no other media
types (books, games, music) and no integrations other than Jellyfin.

## Install

Docker Compose is the recommended way to run MinTrack. Images are published for x86-64 and 64-bit ARM (a Raspberry
Pi 3, 4 or 5 with a 64-bit system).

1. In an empty folder, create `docker-compose.yml`:

   ```yaml
   name: mintrack

   # Settings shared by the MinTrack services, which run the same image.
   x-mintrack: &mintrack
     # A release (1.4.2), a release line (1.4) or latest, set by MINTRACK_VERSION in .env.
     image: ghcr.io/aberrier/mintrack:${MINTRACK_VERSION:-latest}
     restart: unless-stopped
     env_file: .env
     environment: &mintrack-environment
       MINTRACK__DATABASE__HOST: db
       MINTRACK__DATABASE__USER: mintrack
       MINTRACK__DATABASE__PASSWORD: ${POSTGRES_PASSWORD}
       MINTRACK__DATABASE__NAME: mintrack
     read_only: true
     tmpfs: [/tmp]
     cap_drop: [ALL]
     security_opt: [no-new-privileges:true]
     logging: { driver: local }

   services:
     db:
       # Follows PostgreSQL 18 patch releases on every docker compose pull.
       image: postgres:18
       restart: unless-stopped
       environment:
         POSTGRES_USER: mintrack
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
         POSTGRES_DB: mintrack
       volumes:
         - db:/var/lib/postgresql
       healthcheck:
         test: ["CMD", "pg_isready", "-U", "mintrack"]
         interval: 5s
         timeout: 5s
         retries: 10
       security_opt: [no-new-privileges:true]
       logging: { driver: local }

     # Upgrades the database schema, then exits; the server and the worker start after it.
     migrate:
       <<: *mintrack
       command: ["mintrack", "db", "migrate"]
       restart: "no"
       healthcheck:
         disable: true
       depends_on:
         db:
           condition: service_healthy

     server:
       <<: *mintrack
       command: ["mintrack", "server", "--no-migrate"]
       environment:
         <<: *mintrack-environment
         MINTRACK__SERVER__RUN_WORKER: "false"
       ports:
         - "${MINTRACK_BIND:-0.0.0.0}:8000:8000"
       depends_on:
         migrate:
           condition: service_completed_successfully

     # Background jobs: TMDB refreshes, air times, notifications, Jellyfin syncs and imports.
     worker:
       <<: *mintrack
       command: ["mintrack", "worker"]
       healthcheck:
         disable: true
       depends_on:
         migrate:
           condition: service_completed_successfully

   networks:
     default:
       name: mintrack
       # A proxy on the host reaches MinTrack from the gateway address. Change both when the range is taken on the host.
       ipam:
         config:
           - subnet: ${MINTRACK_SUBNET:-172.30.0.0/24}
             gateway: ${MINTRACK_GATEWAY:-172.30.0.1}

   volumes:
     db:
   ```

2. Next to it, create `.env` and keep it private (`chmod 600 .env`). Generate each secret with
   `openssl rand -hex 32`:

   ```dotenv
   POSTGRES_PASSWORD=<a random password>
   MINTRACK__SECURITY__SECRET_KEY=<another random value>
   MINTRACK__PROJECT__PUBLIC_URL=http://localhost:8000
   MINTRACK__TMDB__API_KEY=<your TMDB API key>
   ```

   `MINTRACK__PROJECT__PUBLIC_URL` is the address you open MinTrack at. The TMDB key is free: create a TMDB account,
   then copy the "API Key" from https://www.themoviedb.org/settings/api. Every other setting is listed with its
   default in [`.env.example`](.env.example); each can also be read from a file through a `_FILE` variant, for
   Docker secrets. `MINTRACK_VERSION` picks the image: `latest` (the default) follows every release; see
   [Upgrades and rollback](#upgrades-and-rollback) to pin one.

3. Start it:

   ```bash
   docker compose up -d
   ```

`migrate` upgrades the database schema and exits; then `server` and `worker` start. MinTrack answers on port 8000
(`http://localhost:8000`, or the server's address on your network). `docker compose ps` shows the server as healthy;
if it is not, `docker compose logs migrate server` shows why, with one line per setting to fix.

4. Create the first admin. The command prints a link to open in a browser, where the admin sets their password:

   ```bash
   docker compose exec server mintrack users create-admin admin
   ```

   The admin then invites everyone else from the Admin tab, and shares each printed link by hand (MinTrack
   sends no email). A forgotten password needs a new link: from the Admin tab, or for an admin
   `docker compose exec server mintrack users reset-link USERNAME`.

### Behind a reverse proxy

HTTPS is needed to install MinTrack on a phone and for push notifications. Put any reverse proxy (Caddy,
nginx, Traefik...) in front, serving MinTrack at the root of its own domain, such as `https://mintrack.example.com`
(not under a path). Set HSTS on the proxy. Then, in `.env`:

- `MINTRACK__PROJECT__PUBLIC_URL=https://mintrack.example.com`
- `MINTRACK__SERVER__FORWARDED_ALLOW_IPS` to the proxy's exact address, so MinTrack sees the real client address:
  `172.30.0.1` for a proxy on the same host; for a proxy container, give it a fixed address on the `mintrack` network
  and trust that.
  Never a whole shared subnet: any container on it could pretend to be any client.
- `MINTRACK_BIND=127.0.0.1` when the proxy runs on the same host, so port 8000 is not reachable from outside. Trust
  the proxy address only together with this setting: otherwise clients reaching port 8000 directly can come from
  that same address and forge their own.

Ports Docker publishes bypass host firewalls such as ufw: with the default bind address, port 8000 is open to every
network the machine is on.

The `mintrack` network uses `172.30.0.0/24`. When that range is already taken on the host, set another one with its
gateway in `.env` (`MINTRACK_SUBNET=172.31.0.0/24` and `MINTRACK_GATEWAY=172.31.0.1`), and trust that gateway
instead of `172.30.0.1`.

### Install the app and turn on notifications

Notifications need an `https://` `MINTRACK__PROJECT__PUBLIC_URL`; their keys come from
`MINTRACK__SECURITY__SECRET_KEY`, so there is nothing else to configure. Each device is turned on separately, in
**Profile > Notifications**, which also has a button to send a test notification. MinTrack notifies you when an
episode of a show you are watching or up to date with airs: at its air time when known, otherwise at 9:00 in your
time zone.

- **Android:** open MinTrack in Chrome, then use **Install app** (or **Add to Home screen**) in Chrome's menu.
  Notifications also work in the browser tab without installing.
- **iPhone and iPad (iOS 16.4 or later):** notifications only work in the installed app. Open MinTrack in Safari, tap
  **Share**, then **Add to Home Screen**, and open MinTrack from the Home Screen before turning notifications on.
- **Desktop:** Chrome, Edge, Firefox and Safari can receive notifications in the browser tab.

Changing the secret key changes the notification keys: each device registers again the next time MinTrack is opened
on it.


## Connect an AI assistant (MCP)

MinTrack serves an [MCP](https://modelcontextprotocol.io) server at `/mcp` (Streamable HTTP), so an assistant can
search shows and movies, read a show's progress, mark episodes and movies watched, set a show's status, and list
upcoming and up-next episodes, as you.

1. In MinTrack, open **Profile → API tokens**, name a token after the assistant and copy it: it is shown only once.
   Revoke it there when you no longer use it.
2. Give the assistant the address `https://mintrack.example.com/mcp` and the header
   `Authorization: Bearer <token>`. With Claude Code:

   ```bash
   claude mcp add --transport http mintrack https://mintrack.example.com/mcp --header "Authorization: Bearer <token>"
   ```

   Other clients take the same two settings, usually in a JSON file:

   ```json
   {
     "mcpServers": {
       "mintrack": {
         "type": "http",
         "url": "https://mintrack.example.com/mcp",
         "headers": { "Authorization": "Bearer <token>" }
       }
     }
   }
   ```

A token gives full access to your tracking: use MinTrack over HTTPS, keep the token out of shared files, and revoke
it if it leaks.


## Operating MinTrack

### Background jobs

The `worker` service runs MinTrack's background jobs: TMDB refreshes (daily for shows still airing, weekly for the
others), exact air times, notifications, Jellyfin syncs and imports, four at a time. A job left unfinished by a
stopped worker is retried after 10 minutes. With `MINTRACK__SERVER__RUN_WORKER=true` (the default outside this
`docker-compose.yml`), the server runs them itself, for installs with a single process.

### Imports from the command line

The import card of the profile takes a Yamtrack CSV export or a TV Time GDPR export. An admin can run the same import
for any user from the folder of `docker-compose.yml`, and see the report at once:

```bash
docker compose run --rm -v "$PWD/export.zip:/import/export.zip:ro" server mintrack import alice tvtime /import/export.zip
```

The source is `yamtrack` or `tvtime`; the command prints what was imported and each row it could not match.

### Backups

Everything MinTrack knows is in PostgreSQL. Keep `.env` with it: its secret key encrypts stored credentials. A backup,
from the folder of `docker-compose.yml`:

```bash
(umask 077; docker compose exec -T db pg_dump -U mintrack -Fc mintrack > mintrack-$(date +%F).dump)
```

To restore it, stop MinTrack, restore into a fresh database, start again:

```bash
docker compose stop server worker
docker compose exec -T db dropdb -U mintrack --force mintrack
docker compose exec -T db createdb -U mintrack mintrack
docker compose exec -T db pg_restore -U mintrack -d mintrack --no-owner < mintrack-2026-01-31.dump
docker compose up -d
```

A fresh database, rather than `pg_restore --clean` over the current one, leaves nothing a later version added
(tables, columns, jobs) behind.

### Upgrades and rollback

`MINTRACK_VERSION` in `.env` picks the image: `latest` (the default) follows every release, `1.4` follows the patch
releases of 1.4, and `1.4.2` stays on that release. Releases are listed on the
[packages page](https://github.com/aberrier/mintrack/pkgs/container/mintrack). To upgrade, take a backup, then:

```bash
docker compose pull
docker compose up -d
```

`migrate` upgrades the database schema before the server and the worker start. Schema upgrades are not reversible,
and an older version refuses to start on a database a newer one migrated. To roll back:

1. Stop MinTrack: `docker compose stop server worker`.
2. Pin the version you came from, such as `MINTRACK_VERSION=1.4.2` in `.env`.
3. Restore the backup taken before the upgrade into a fresh database, as in [Backups](#backups), which ends with
   `docker compose up -d`.

### PostgreSQL major upgrades

`postgres:18` follows minor releases only. Moving to a new major version (19, for example) needs a dump and a restore
into a new volume:

1. Take a backup as above, then `docker compose down`.
2. Change the image to `postgres:19` and the volume name (`db` to `db19`, in `services.db.volumes` and `volumes`).
3. Start the database alone, restore, then start everything:

   ```bash
   docker compose up -d db
   docker compose exec -T db pg_restore -U mintrack -d mintrack --clean --if-exists < mintrack-2026-01-31.dump
   docker compose up -d
   ```

Keep the old volume until MinTrack works on the new one; `docker volume rm mintrack_db` then frees it.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy and Alembic on PostgreSQL, with
  Procrastinate for background jobs (no Redis).
- **Frontend:** Angular with Angular Material, shipped as an installable web
  app (PWA) with Web Push, in `frontend/`.
- **Metadata:** TMDB, plus TVmaze for episode air times.
- **Deployment:** one Docker image and a docker-compose file with PostgreSQL.

## Origins

MinTrack is a from-scratch rewrite inspired by
[Yamtrack](https://github.com/FuzzyGrim/Yamtrack) and its fork
[Floppy](https://github.com/dannyvfilms/Floppy). Thanks to their authors and
contributors for the groundwork.

## License

AGPL-3.0. See [LICENSE](LICENSE).
