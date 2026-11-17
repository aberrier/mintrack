<p align="center">
  <b>MinTrack: a minimal, self-hosted TV and movie tracker with the TV Time experience.</b><br>
  Track movies, TV shows and anime, mark episodes in one tap, and get notified when new ones air.
</p>

MinTrack is a small media tracker you run on your own server, for yourself and a
few friends. It focuses on the things TV Time did well on a phone: knowing which
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
  administer (yours, a friend's). What you watch there shows up in MinTrack
  within minutes.
- **Small and private.** A few users per instance, invited by the admin. No
  email, no social features, no tracking.

## What it does not do

No social network, no recommendations, no ratings or reviews, no other media
types (books, games, music) and no integrations other than Jellyfin.

## Planned stack

- **Backend:** Python, FastAPI, SQLAlchemy and Alembic on PostgreSQL, with
  Procrastinate for background jobs (no Redis).
- **Frontend:** Angular with Angular Material, shipped as an installable web
  app (PWA) with Web Push. It will live in `frontend/`.
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
