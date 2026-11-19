<p align="center">
  <img src="frontend/public/icons/icon.svg" alt="" width="96" height="96"><br>
  <b>MinTrack: a minimal, self-hosted TV and movie tracker with the TV Time experience.</b><br>
  Track movies, TV shows and anime, mark episodes in one tap, and get notified when new ones air.
</p>

MinTrack is a small media tracker you run on your own server, for yourself and the
people you share it with. It focuses on the things TV Time did well on a phone: knowing which
episode comes next, what airs soon, and marking what you watched without friction.
Your Jellyfin servers fill in your history on their own.

> **Status:** young and before 1.0: expect changes between releases, and read the release notes before upgrading.

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
- **Digital release alerts** for the movies on your watch later list.
- **Several Jellyfin accounts per user**, even on servers you don't
  administer, linked with Quick Connect: MinTrack never sees your Jellyfin
  password. What you watch there shows up in MinTrack within minutes.
- **Easy to self-host and private.** One docker-compose file, several users
  per instance, invited by the admin. No email, no social features, no tracking.
- **An MCP server** so an AI assistant (Claude Code, Claude Desktop...) can read
  and update your tracking, with a token you create in **Profile › Settings**.
- **Imports from Yamtrack and TV Time**, from **Profile › Settings**, with watch
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
- **Episode details and your own ratings.** Tap an episode for its synopsis,
  air date and TMDB score, to mark it or change when you watched it. Rate
  episodes, shows and movies with 1 to 5 stars and a short review, seen only
  by you.
- **Statistics** in **Profile**, private to you: time spent watching (from TMDB
  runtimes; an episode without one counts its show's average, and what has no
  runtime at all is left out and counted apart), episodes and movies per month
  over the last year, current and longest streaks of days, top genres and
  networks, and totals.

## What it does not do

No social network, no recommendations, no shared ratings or reviews, no other
media types (books, games, music) and no integrations other than Jellyfin.

## Install

Docker Compose is the recommended way to run MinTrack. Images are published for x86-64 and 64-bit ARM (a Raspberry
Pi 3, 4 or 5 with a 64-bit system). Everything is in one file: there is no `.env` to write.

1. In an empty folder, create `docker-compose.yml` with this content, and keep it private
   (`chmod 600 docker-compose.yml`): it holds the secrets.

   ```yaml
   name: mintrack

   # Edit the four values marked EDIT, then `docker compose up -d`. Keep this file private (chmod 600): it holds the
   # secrets. Every other setting and its default is in the README, under Configuration.

   x-database-password: &database-password change-me # EDIT: the output of `openssl rand -hex 32`, before the first start

   # Settings shared by the MinTrack services, which run the same image.
   x-mintrack: &mintrack
     # latest follows every release; a release line (1.4) or a release (1.4.2) pins it.
     image: ghcr.io/aberrier/mintrack:latest
     restart: unless-stopped
     environment: &mintrack-environment
       # EDIT: the address you open MinTrack at, the root of an origin. Installing the app and push need https://.
       MINTRACK__PROJECT__PUBLIC_URL: http://localhost:8000
       # EDIT: the output of `openssl rand -hex 32`. Back it up: it encrypts the stored Jellyfin tokens.
       MINTRACK__SECURITY__SECRET_KEY: change-me-to-the-output-of-openssl-rand-hex-32
       # EDIT: your TMDB API key (free, https://www.themoviedb.org/settings/api). Empty: no search and no new pages.
       MINTRACK__TMDB__API_KEY: ""
       # Behind a reverse proxy on this host: the gateway of the network below, from which the proxy connects.
       # MINTRACK__SERVER__FORWARDED_ALLOW_IPS: 172.30.0.1
       MINTRACK__DATABASE__HOST: db
       MINTRACK__DATABASE__USER: mintrack
       MINTRACK__DATABASE__PASSWORD: *database-password
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
         POSTGRES_PASSWORD: *database-password
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
         # Behind a reverse proxy on this host: "127.0.0.1:8000:8000", so only the proxy reaches it.
         - "0.0.0.0:8000:8000"
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
       # A proxy on the host reaches MinTrack from the gateway address. Change both when the range is taken on the host,
       # as by a second MinTrack.
       ipam:
         config:
           - subnet: 172.30.0.0/24
             gateway: 172.30.0.1

   volumes:
     db:
   ```

2. Edit the four values marked `EDIT`:
   - The database password and the secret key: run `openssl rand -hex 32` twice and paste one output into each. The
     database password is set when the database is first created.
   - `MINTRACK__PROJECT__PUBLIC_URL`: the address you open MinTrack at, such as `http://192.168.1.10:8000` or, behind
     a reverse proxy, `https://mintrack.example.com`.
   - `MINTRACK__TMDB__API_KEY`: the TMDB key is free: create a TMDB account, then copy the "API Key" from
     https://www.themoviedb.org/settings/api.

   The image line picks the version: `latest` follows every release; see
   [Upgrades and rollback](#upgrades-and-rollback) to pin one.

3. Start it:

   ```bash
   docker compose up -d
   ```

   `migrate` upgrades the database schema and exits; then `server` and `worker` start. MinTrack answers on port 8000.
   `docker compose ps` shows the server as healthy; if it is not, `docker compose logs migrate server` shows why, with
   one line per setting to fix.

4. Open MinTrack and create the admin account: while no account exists, the login page offers it. Or, from the
   command line, create the admin and open the link it prints to set their password:

   ```bash
   docker compose exec server mintrack users create-admin admin
   ```

   To keep an instance reachable by others closed until the admin exists, add `MINTRACK__ACCOUNTS__SETUP: "false"`
   and use the command. The admin then invites everyone else from the Admin tab, and shares each printed link by hand
   (MinTrack sends no email). A forgotten password needs a new link: from the Admin tab, or for an admin
   `docker compose exec server mintrack users reset-link USERNAME`. A link is shown once, so copy it right away; an
   invitation link lasts 7 days and a reset link 24 hours, and a new link for the same user replaces the previous
   one. A refused link tells its holder why: expired, already used or replaced.

### Configuration

Settings are environment variables of the `migrate`, `server` and `worker` services, in the `environment` block that
`docker-compose.yml` shares between them. Each can also be read from a file through a `_FILE` variant, for Docker
secrets: `MINTRACK__SECURITY__SECRET_KEY_FILE: /run/secrets/mintrack_secret_key`.

| Variable | Default | Meaning |
|---|---|---|
| `MINTRACK__PROJECT__PUBLIC_URL` | `http://localhost:8000` | The address MinTrack is opened at, the root of an origin (no path). |
| `MINTRACK__SECURITY__SECRET_KEY` | required | At least 32 characters. Changing it makes the stored Jellyfin tokens unreadable (link the accounts again) and each device register for notifications again. |
| `MINTRACK__TMDB__API_KEY` | none | Without it, search and new pages are unavailable. |
| `MINTRACK__TMDB__LANGUAGE` | `en` | Language of titles and overviews, such as `fr` or `pt-BR`; after a change, titles in a library are fetched again within the hour, the others when next opened. |
| `MINTRACK__ACCOUNTS__SETUP` | `true` | While no account exists, the login page offers to create the admin account. |
| `MINTRACK__SERVER__FORWARDED_ALLOW_IPS` | none | The reverse proxy's exact address, allowed to set `X-Forwarded-For` and `X-Forwarded-Proto`. |
| `MINTRACK__DATABASE__HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_NAME` | port `5432` | The PostgreSQL database. |
| `MINTRACK__DATABASE__SSLMODE` | none | `disable`, `allow`, `prefer`, `require`, `verify-ca` or `verify-full`, for an external PostgreSQL. |
| `MINTRACK__SERVER__RUN_WORKER` | `true` | The server runs the background jobs itself; `false` when `mintrack worker` runs as its own service. |
| `MINTRACK__LOGGING__FORMAT` | `console` | `console` or `json`. |
| `MINTRACK__LOGGING__LEVEL` | `info` | `debug`, `info`, `warning`, `error` or `critical`. |
| `MINTRACK__LOGGING__SENTRY_DSN` | none | Error reporting, off unless set; no personal data is sent. |
| `MINTRACK__LOGGING__SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Share of requests traced for performance. |

### Behind a reverse proxy

HTTPS is needed to install MinTrack on a phone and for push notifications. Put any reverse proxy (Caddy,
nginx, Traefik...) in front, serving MinTrack at the root of its own domain, such as `https://mintrack.example.com`
(not under a path). Set HSTS on the proxy. Then, in `docker-compose.yml`:

- `MINTRACK__PROJECT__PUBLIC_URL: https://mintrack.example.com`.
- `MINTRACK__SERVER__FORWARDED_ALLOW_IPS` to the address the proxy connects from, so MinTrack sees the real client
  address. A proxy on the same host connects from the network's gateway, `172.30.0.1`. A proxy container joins the
  project's network (`mintrack_default`) with a fixed address, and that address is the one to trust. Never a whole
  shared subnet: any container on it could pretend to be any client.
- With the proxy on the same host, publish the port as `127.0.0.1:8000:8000`, so port 8000 is not reachable from
  outside. Trust the proxy address only together with this setting: otherwise clients reaching port 8000 directly can
  come from that same address and forge their own.

Ports Docker publishes bypass host firewalls such as ufw: with `0.0.0.0`, port 8000 is open to every network the
machine is on.

The network uses `172.30.0.0/24`. When that range is already taken on the host, set another subnet and gateway at
the end of `docker-compose.yml`, such as `172.31.0.0/24` and `172.31.0.1`, and trust that gateway instead of
`172.30.0.1`. A second MinTrack on the same host needs, besides its own range, another project name (the `name:`
line) and another published port.

### Install the app and turn on notifications

Notifications need an `https://` `MINTRACK__PROJECT__PUBLIC_URL`; their keys come from
`MINTRACK__SECURITY__SECRET_KEY`, so there is nothing else to configure. Each device is turned on separately, in
**Profile › Settings › Notifications**, which also has a button to send a test notification. MinTrack notifies you
when an episode of a show you are watching or up to date with airs: at its air time when known, otherwise at 9:00 in
your time zone.

It also notifies you, once, when a movie on your watch later list is released digitally (to rent, buy or stream):
the first digital release TMDB lists, in any country, checked every day at 08:00 UTC.

- **Android (Chrome):** open MinTrack's address in Chrome › menu **⋮** › **Install app** (or **Add to Home screen**)
  › open MinTrack from the Home screen › **Profile › Settings › Notifications** › turn it on › **Allow**.
  Notifications also work in the browser tab without installing. If nothing arrives: turn notifications on in
  Android **Settings › Apps › MinTrack** (or Chrome) **› Notifications**, and turn off battery saver and **Pause app
  activity if unused**.
- **iPhone and iPad (iOS 16.4 or later):** open the address in Safari › **Share** › **Add to Home Screen** › open
  MinTrack from the Home Screen (notifications do not work in a Safari tab) › **Profile › Settings › Notifications**
  › turn it on › **Allow**. If nothing arrives: allow them in iOS **Settings › Notifications › MinTrack**; a Focus
  mode can hold them back.
- **Desktop:** Chrome, Edge, Firefox and Safari can receive notifications in the browser tab.

**Send a test notification** in the same settings checks the whole chain. The app shows these steps too, under **How
to get notifications** in the Notifications settings.

Changing the secret key changes the notification keys: each device registers again the next time MinTrack is opened
on it.


## Connect an AI assistant (MCP)

MinTrack serves an [MCP](https://modelcontextprotocol.io) server at `/mcp` (Streamable HTTP), so an assistant can
search shows and movies, read a show's progress, mark episodes and movies watched, set a show's status, and list
upcoming episodes and the watch list, as you. In the app, **Learn more** under **Profile › Settings › API tokens**
walks through these steps with this server's address filled in.

1. In MinTrack, open **Profile › Settings › API tokens**, name a token after the assistant and copy it: it is shown
   only once. Revoke it there when you no longer use it.
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

The import card of **Profile › Settings** takes a Yamtrack CSV export or a TV Time GDPR export. An admin can run the
same import for any user from the folder of `docker-compose.yml`, and see the report at once:

```bash
docker compose run --rm -v "$PWD/export.zip:/import/export.zip:ro" server mintrack import alice tvtime /import/export.zip
```

The source is `yamtrack` or `tvtime`; the command prints what was imported and each row it could not match.

### Backups

Everything MinTrack knows is in PostgreSQL. Keep `docker-compose.yml` with it: its secret key encrypts stored
credentials. A backup, from the folder of `docker-compose.yml`:

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

The image line of `docker-compose.yml` picks the version: `ghcr.io/aberrier/mintrack:latest` follows every release,
`ghcr.io/aberrier/mintrack:1.4` the patch releases of 1.4, and `ghcr.io/aberrier/mintrack:1.4.2` stays on that
release. Releases are listed on the [packages page](https://github.com/aberrier/mintrack/pkgs/container/mintrack);
**Profile › Settings** shows the version running. To upgrade, take a backup, then:

```bash
docker compose pull
docker compose up -d
```

`migrate` upgrades the database schema before the server and the worker start. Schema upgrades are not reversible,
and an older version refuses to start on a database a newer one migrated. To roll back:

1. Stop MinTrack: `docker compose stop server worker`.
2. Pin the version you came from in the image line, such as `ghcr.io/aberrier/mintrack:1.4.2`.
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

## Releases

1. On a clean, up-to-date `master`, run `just release 1.4.2`: it sets the version, commits it and tags `v1.4.2`.
   A release candidate, `just release 1.4.2-rc.1`, can be cut from any branch: it publishes only the image
   `1.4.2-rc.1`, with a GitHub pre-release.
2. Push as it prints: `git push --atomic origin master v1.4.2`. Push tags one at a time: GitHub starts no workflow
   for a push of more than three tags.
3. The Release workflow checks the tag against the version, publishes the image and creates the GitHub release.
4. After the very first publish only: in the package's settings on GitHub, change its visibility to Public (anonymous
   `docker pull` fails otherwise) and connect it to this repository.

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
