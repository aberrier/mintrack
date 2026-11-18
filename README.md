<p align="center">
  <b>MinTrack: a minimal, self-hosted TV and movie tracker with the TV Time experience.</b><br>
  Track movies, TV shows and anime, mark episodes in one tap, and get notified when new ones air.
</p>

MinTrack is a small media tracker you run on your own server, for yourself and the
people you share it with. It focuses on the things TV Time did well on a phone: knowing which
episode comes next, what airs soon, and marking what you watched without friction.
Your Jellyfin servers fill in your history on their own.

> **Status:** early development. Nothing is usable yet; this README describes
> what the project is building.

## What it does

- **Movies, TV shows and anime.** Anime are tracked as regular TV shows, with
  metadata from TMDB.
- **One tap to mark an episode watched**, another tap to unmark it. Two taps
  to mark a whole season. When you skip ahead, MinTrack offers to mark the
  previous episodes too.
- **TV Time statuses.** Watch later, watching, up to date, finished and stopped.
  Most of them follow your progress automatically.
- **Up next and upcoming.** The next episode of every show you watch, and
  what airs soon, with real air times when available.
- **Push notifications** when a new episode of a show you follow airs, on
  Android and iOS, through an installable web app. No app store needed.
- **Several Jellyfin accounts per user**, even on servers you don't
  administer. What you watch there shows up in MinTrack
  within minutes.
- **Easy to self-host and private.** One docker-compose file, several users
  per instance, invited by the admin. No email, no social features, no tracking.

## What it does not do

No social network, no recommendations, no ratings or reviews, no other media
types (books, games, music) and no integrations other than Jellyfin.

## Install

Docker Compose is the recommended way to run MinTrack. Images are published for x86-64 and 64-bit ARM (a Raspberry
Pi 3, 4 or 5 with a 64-bit system).

1. In an empty folder, create `docker-compose.yml`:

   ```yaml
   name: mintrack

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

     server:
       image: ghcr.io/aberrier/mintrack:edge
       restart: unless-stopped
       depends_on:
         db:
           condition: service_healthy
       env_file: .env
       environment:
         MINTRACK__DATABASE__HOST: db
         MINTRACK__DATABASE__USER: mintrack
         MINTRACK__DATABASE__PASSWORD: ${POSTGRES_PASSWORD}
         MINTRACK__DATABASE__NAME: mintrack
       ports:
         - "${MINTRACK_BIND:-0.0.0.0}:8000:8000"
       read_only: true
       tmpfs: [/tmp]
       cap_drop: [ALL]
       security_opt: [no-new-privileges:true]
       logging: { driver: local }

   networks:
     default:
       name: mintrack
       # A proxy on the host reaches MinTrack from the gateway address.
       ipam:
         config:
           - subnet: 172.30.0.0/24
             gateway: 172.30.0.1

   volumes:
     db:
   ```

2. Next to it, create `.env` and keep it private (`chmod 600 .env`). Generate each secret with
   `openssl rand -hex 32`:

   ```dotenv
   POSTGRES_PASSWORD=<a random password>
   MINTRACK__SECURITY__SECRET_KEY=<another random value>
   MINTRACK__PROJECT__PUBLIC_URL=http://localhost:8000
   ```

   `MINTRACK__PROJECT__PUBLIC_URL` is the address you open MinTrack at. Every other setting is listed with its
   default in [`.env.example`](.env.example); each can also be read from a file through a `_FILE` variant, for
   Docker secrets.

3. Start it:

   ```bash
   docker compose up -d
   ```

MinTrack answers on port 8000 (`http://localhost:8000`, or the server's address on your network). `docker compose ps`
shows it as healthy; if it is not, `docker compose logs server` shows why, with one line per setting to fix.

4. Create the first admin. The command prints a link to open in a browser, where the admin sets their password:

   ```bash
   docker compose exec server mintrack users create-admin admin
   ```

   The admin then invites everyone else from Profile > Manage users, and shares each printed link by hand (MinTrack
   sends no email). A forgotten password needs a new link: from the users page, or for an admin
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


## Stack

- **Backend:** Python, FastAPI, SQLAlchemy and Alembic on PostgreSQL, with
  Procrastinate for background jobs (no Redis).
- **Frontend:** Angular with Angular Material, shipped as an installable web
  app (PWA) with Web Push, in `frontend/`.
- **Metadata:** TMDB, plus TVmaze for episode air times.
- **Deployment:** one Docker image and a docker-compose file with PostgreSQL.

## Roadmap

1. Foundations: project skeleton, Docker, CI, linting and tests.
2. Accounts: login, sessions, admin invitations.
3. Catalog and tracking: TMDB search, shows and movies, one-tap episodes, statuses.
4. Upcoming episodes and calendar, with TVmaze air times.
5. Installable app and push notifications.
6. Jellyfin sync with several accounts per user.
7. Imports from Yamtrack and TV Time.
8. MCP server.

## Origins

MinTrack is a from-scratch rewrite inspired by
[Yamtrack](https://github.com/FuzzyGrim/Yamtrack) and its fork
[Floppy](https://github.com/dannyvfilms/Floppy). Thanks to their authors and
contributors for the groundwork.

## License

AGPL-3.0. See [LICENSE](LICENSE).
