import asyncio
import collections.abc
import datetime as dt
import uuid
import zoneinfo

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from mintrack.core.catalog.managers import CatalogManager, episode_code
from mintrack.core.tracking.managers import ShowTrackingChoice, TrackingManager
from mintrack.db.models import (
    Episode,
    ImportJob,
    ImportReport,
    ImportSource,
    ImportStatus,
    Media,
    MediaType,
    User,
    UserMedia,
    WatchedEpisode,
    WatchedMovie,
)
from mintrack.integrations.tmdb.client import ExternalSource, TMDBClient, TMDBError, TMDBNotFoundError
from mintrack.observability.logging import logger
from mintrack.worker.defer import defer_import

from .parsers import (
    EpisodeRow,
    ImportRow,
    MovieRow,
    ShowRow,
    SkippedRow,
    UnmatchedReason,
    keep_tvtime_tracking_files,
    parse_tvtime,
    parse_yamtrack,
)

ACTIVE_STATUSES = (ImportStatus.PENDING, ImportStatus.RUNNING)
# A job without progress for this long and without a task to run it was lost, and no longer blocks a new import.
STALE_AFTER = dt.timedelta(minutes=15)
_PROCRASTINATE_JOBS = sa.table("procrastinate_jobs", sa.column("queueing_lock"), sa.column("status"))
PROGRESS_EVERY = 50
MAX_REPORTED_UNMATCHED = 500

_PARSERS = {ImportSource.YAMTRACK: parse_yamtrack, ImportSource.TVTIME: parse_tvtime}


class ImportInProgressError(Exception):
    """The user already has an import pending or running."""


def parse(source: ImportSource, data: bytes, timezone: str) -> list[ImportRow]:
    return _PARSERS[source](data, zoneinfo.ZoneInfo(timezone))


def _validate(source: ImportSource, data: bytes, timezone: str) -> bytes:
    """The file to keep for the job: parsed once to refuse a wrong file, a TV Time archive cut to its tracking files."""
    parse(source, data, timezone)
    return keep_tvtime_tracking_files(data) if source is ImportSource.TVTIME else data


class ImportManager:
    def __init__(self, session: AsyncSession, tmdb: TMDBClient) -> None:
        self.session = session
        self.tmdb = tmdb

    async def create(
        self, user: User, source: ImportSource, filename: str, data: bytes, *, queue: bool = True
    ) -> ImportJob:
        """Validate the file and queue it for the worker, unless the caller runs it; raises `ImportInProgressError` or
        `ImportFileError`."""
        now = dt.datetime.now(dt.UTC)
        await self._expire_lost(now)
        active = sa.select(ImportJob.id).where(ImportJob.user_id == user.id, ImportJob.status.in_(ACTIVE_STATUSES))
        if await self.session.scalar(active) is not None:
            raise ImportInProgressError
        data = await asyncio.to_thread(_validate, source, data, user.timezone)
        job = ImportJob(user_id=user.id, source=source, filename=filename, file=data, updated_at=now)
        try:
            async with self.session.begin_nested():
                self.session.add(job)
        except IntegrityError as error:
            raise ImportInProgressError from error
        if queue:
            await defer_import(self.session, job.id, user.id)
        return job

    async def latest(self, user: User) -> ImportJob | None:
        await self._expire_lost(dt.datetime.now(dt.UTC))
        return await self.session.scalar(
            sa.select(ImportJob).filter_by(user_id=user.id).order_by(ImportJob.created_at.desc()).limit(1)
        )

    async def run(self, job_id: uuid.UUID) -> None:
        """Import the rows of a pending job, or start again one whose worker stopped, then drop its file whatever the
        outcome."""
        job = await self.session.get(ImportJob, job_id, options=[undefer(ImportJob.file)])
        if job is None or job.status not in ACTIVE_STATUSES or job.file is None:
            return
        user = await self.session.get_one(User, job.user_id)
        job.status, job.updated_at = ImportStatus.RUNNING, dt.datetime.now(dt.UTC)
        await self.session.commit()

        try:
            rows = await asyncio.to_thread(parse, job.source, job.file, user.timezone)
            job.total = len(rows)
            importer = _Importer(self.session, self.tmdb, user, started_at=job.updated_at)
            await importer.load()
            for index, row in enumerate(rows, start=1):
                await importer.apply(row)
                if index % PROGRESS_EVERY == 0:
                    await importer.refresh_statuses()
                    job.processed, job.updated_at = index, dt.datetime.now(dt.UTC)
                    await self.session.commit()
            await importer.refresh_statuses()
            job.processed, job.report = len(rows), importer.report()
            job.status = ImportStatus.DONE
            job.file, job.finished_at = None, dt.datetime.now(dt.UTC)
            await self.session.commit()
        except asyncio.CancelledError:
            # The worker is shutting down: the job would otherwise stay running.
            await self._fail(job_id)
            raise
        except Exception:  # noqa: BLE001
            logger.exception("import failed", job_id=str(job_id))
            await self._fail(job_id)

    async def _fail(self, job_id: uuid.UUID) -> None:
        await self.session.rollback()
        now = dt.datetime.now(dt.UTC)
        await self.session.execute(
            sa.update(ImportJob)
            .where(ImportJob.id == job_id)
            .values(status=ImportStatus.FAILED, file=None, finished_at=now, updated_at=now)
        )
        await self.session.commit()

    async def _expire_lost(self, now: dt.datetime) -> None:
        """Fail the jobs without progress for STALE_AFTER whose task is no longer queued or running (the queue was
        cleared): nothing would finish them. A task waiting in the queue, or retried after its worker stopped, still
        will."""
        queued = sa.exists().where(
            _PROCRASTINATE_JOBS.c.queueing_lock == sa.func.concat("import:", ImportJob.id),
            sa.cast(_PROCRASTINATE_JOBS.c.status, sa.TEXT).in_(["todo", "doing"]),
        )
        await self.session.execute(
            sa.update(ImportJob)
            .where(ImportJob.status.in_(ACTIVE_STATUSES), ImportJob.updated_at < now - STALE_AFTER, ~queued)
            .values(status=ImportStatus.FAILED, file=None, finished_at=now)
            .execution_options(synchronize_session=False)
        )


class _Importer:
    """Matches rows to TMDB and records them, counting what was imported, already there or left unmatched.

    What the user already has is kept as it is: a show or movie in the library keeps its status, a watched episode or
    movie its date.
    """

    def __init__(self, session: AsyncSession, tmdb: TMDBClient, user: User, started_at: dt.datetime) -> None:
        self.session = session
        self.tmdb = tmdb
        self.user = user
        self.started_at = started_at
        self.catalog = CatalogManager(session, tmdb)
        self.tracking = TrackingManager(session)
        self.imported = 0
        self.already_present = 0
        self.unmatched: dict[tuple[str, UnmatchedReason], None] = {}
        self.lookups: dict[tuple[object, ...], int | None] = {}
        self.found_episodes: dict[int, tuple[int, int, int] | None] = {}
        self.media: dict[tuple[int, MediaType], Media | UnmatchedReason] = {}
        self.episodes: dict[uuid.UUID, dict[tuple[int, int], Episode]] = {}
        self.tracked: set[uuid.UUID] = set()
        self.watched_episodes: set[uuid.UUID] = set()
        self.watched_movies: set[uuid.UUID] = set()
        # Shows added stopped or put aside: marking their episodes does not resume them.
        self.set_aside: set[uuid.UUID] = set()
        # Episodes to mark at the next `refresh_statuses`, per show.
        self.marked: dict[Media, dict[uuid.UUID, dt.datetime]] = {}
        # The title of the per-season entry (MyAnimeList, AniList) that matched each show first.
        self.season_entries: dict[uuid.UUID, str] = {}

    async def load(self) -> None:
        """The user's library and watches, so each row is checked without a query."""
        user_id = self.user.id
        self.tracked = set(await self.session.scalars(sa.select(UserMedia.media_id).filter_by(user_id=user_id)))
        self.watched_episodes = set(
            await self.session.scalars(sa.select(WatchedEpisode.episode_id).filter_by(user_id=user_id))
        )
        self.watched_movies = set(
            await self.session.scalars(sa.select(WatchedMovie.media_id).filter_by(user_id=user_id))
        )

    async def refresh_statuses(self) -> None:
        """Record the episodes marked since the last call, and compute the status of their shows once."""
        await self.tracking.record_watches(self.user, self.marked, now=self.started_at, keep_aside=self.set_aside)
        self.marked.clear()

    def report(self) -> ImportReport:
        return {
            "imported": self.imported,
            "already_present": self.already_present,
            "unmatched_count": len(self.unmatched),
            "unmatched": [
                {"title": title, "reason": reason} for title, reason in list(self.unmatched)[:MAX_REPORTED_UNMATCHED]
            ],
        }

    async def apply(self, row: ImportRow) -> None:
        match row:
            case SkippedRow():
                self._unmatched(row.title, row.reason)
            case ShowRow():
                await self._apply_show(row)
            case EpisodeRow():
                await self._apply_episode(row)
            case MovieRow():
                await self._apply_movie(row)

    def _unmatched(self, title: str, reason: UnmatchedReason) -> None:
        self.unmatched[title, reason] = None

    def _count(self, *, imported: bool) -> None:
        if imported:
            self.imported += 1
        else:
            self.already_present += 1

    async def _apply_show(self, row: ShowRow) -> None:
        media = await self._match(row, MediaType.TV)
        if isinstance(media, UnmatchedReason):
            self._unmatched(row.title, media)
            return
        # Another season's entry matched by title to the same show: its episodes are not guessed.
        if row.season_entry and self.season_entries.setdefault(media.id, row.title) != row.title:
            self._unmatched(row.title, UnmatchedReason.TO_CHECK)
            return
        if media.id in self.tracked:
            self._count(imported=False)
            return
        status = (
            ShowTrackingChoice.STOPPED
            if row.stopped
            else ShowTrackingChoice.WATCH_LATER
            if row.watch_later
            else ShowTrackingChoice.WATCHING
        )
        await self.tracking.set_show_status(self.user, media, status, self.started_at)
        self.tracked.add(media.id)
        if status is not ShowTrackingChoice.WATCHING:
            self.set_aside.add(media.id)
        if row.progress:
            episodes = sorted((key, episode) for key, episode in (await self._episodes(media)).items() if key[0])
            await self._mark(media, [episode for _, episode in episodes[: row.progress]], row.watched_at)
        self._count(imported=True)

    async def _apply_episode(self, row: EpisodeRow) -> None:
        season, number = row.season, row.episode
        if (season is None or number is None) and row.ids.tvdb_episode is not None:
            found = await self._find_episode(row.ids.tvdb_episode)
            if found is not None:
                _, season, number = found
        media = await self._match(row, MediaType.TV)
        if isinstance(media, UnmatchedReason):
            self._unmatched(row.title, media)
            return
        episode = None if season is None or number is None else (await self._episodes(media)).get((season, number))
        if episode is None and row.ids.tvdb_episode is not None:
            # TVDB and TMDB may split seasons differently: TMDB knows where TVDB's episode is.
            media, episode = await self._episode_by_tvdb_id(row.ids.tvdb_episode, media)
        if episode is None:
            label = row.title if season is None or number is None else f"{row.title} {episode_code(season, number)}"
            self._unmatched(label, UnmatchedReason.EPISODE_NOT_FOUND)
            return
        if episode.id in self.watched_episodes:
            self._count(imported=False)
            return
        await self._mark(media, [episode], row.watched_at)
        self._count(imported=True)

    async def _episode_by_tvdb_id(self, tvdb_episode_id: int, media: Media) -> tuple[Media, Episode | None]:
        """The episode TMDB maps the TVDB episode to, in `media` or in the TMDB show it belongs to."""
        found = await self._find_episode(tvdb_episode_id)
        if found is None:
            return media, None
        show_id, season, number = found
        if show_id != media.tmdb_id:
            other = await self._match_tmdb(show_id, MediaType.TV)
            if isinstance(other, UnmatchedReason):
                return media, None
            media = other
        return media, (await self._episodes(media)).get((season, number))

    async def _mark(self, media: Media, episodes: list[Episode], at: dt.datetime | None) -> None:
        if not episodes:
            return
        # A date after the import started (a clock or time zone mistake in the export) is the import's.
        self.marked.setdefault(media, {}).update(
            dict.fromkeys((episode.id for episode in episodes), at or self.started_at)
        )
        self.watched_episodes.update(episode.id for episode in episodes)
        self.tracked.add(media.id)

    async def _apply_movie(self, row: MovieRow) -> None:
        media = await self._match(row, MediaType.MOVIE)
        if isinstance(media, UnmatchedReason):
            self._unmatched(row.title, media)
            return
        if media.id in self.watched_movies or (not row.watched and media.id in self.tracked):
            self._count(imported=False)
            return
        # A date after the import started is the import's, as for episodes.
        at = min(row.watched_at or self.started_at, self.started_at)
        await self.tracking.set_movie_watched(self.user, media, watched=row.watched, at=at, now=self.started_at)
        self.tracked.add(media.id)
        if row.watched:
            self.watched_movies.add(media.id)
        self._count(imported=True)

    async def _match(self, row: ShowRow | EpisodeRow | MovieRow, media_type: MediaType) -> Media | UnmatchedReason:
        try:
            tmdb_id = await (self._movie_id(row) if isinstance(row, MovieRow) else self._show_id(row))
        except TMDBError:
            return UnmatchedReason.TMDB_UNAVAILABLE
        if tmdb_id is None:
            return UnmatchedReason.NOT_FOUND
        return await self._match_tmdb(tmdb_id, media_type)

    async def _match_tmdb(self, tmdb_id: int, media_type: MediaType) -> Media | UnmatchedReason:
        key = (tmdb_id, media_type)
        if key not in self.media:
            try:
                self.media[key] = await self.catalog.get_or_fetch(media_type, tmdb_id, self.started_at)
            except TMDBNotFoundError:
                self.media[key] = UnmatchedReason.NOT_FOUND
            except TMDBError:
                return UnmatchedReason.TMDB_UNAVAILABLE
        return self.media[key]

    async def _show_id(self, row: ShowRow | EpisodeRow) -> int | None:
        ids = row.ids
        if ids.tmdb is not None:
            return ids.tmdb
        if (tvdb_id := ids.tvdb) is not None:
            return await self._lookup(("tvdb", tvdb_id), lambda: self._find_show(tvdb_id))
        if not row.title:
            return None
        # TV Time rows without a show id: the show of the first episode found stands for the whole title.
        if isinstance(row, EpisodeRow) and ids.tvdb_episode is not None and ("title", row.title) not in self.lookups:
            found = await self._find_episode(ids.tvdb_episode)
            if found is not None:
                self.lookups["title", row.title] = found[0]
        return await self._lookup(("title", row.title), lambda: self._search(row.title, MediaType.TV, None))

    async def _movie_id(self, row: MovieRow) -> int | None:
        if row.ids.tmdb is not None:
            return row.ids.tmdb
        if (imdb_id := row.ids.imdb) is not None:
            return await self._lookup(("imdb", imdb_id), lambda: self._find_movie(imdb_id))
        if not row.title:
            return None
        return await self._lookup(
            ("movie", row.title, row.year), lambda: self._search(row.title, MediaType.MOVIE, row.year)
        )

    async def _lookup(
        self, key: tuple[object, ...], query: collections.abc.Callable[[], collections.abc.Awaitable[int | None]]
    ) -> int | None:
        if key not in self.lookups:
            self.lookups[key] = await query()
        return self.lookups[key]

    async def _search(self, title: str, media_type: MediaType, year: int | None) -> int | None:
        """The first search result of that type, and of that year when known."""
        results = await self.tmdb.search(title)
        return next(
            (
                result.id
                for result in results
                if result.media_type == media_type
                and (year is None or (result.release_date is not None and result.release_date.year == year))
            ),
            None,
        )

    async def _find_show(self, tvdb_id: int) -> int | None:
        results = (await self.tmdb.find(str(tvdb_id), ExternalSource.TVDB)).get("tv_results") or []
        return results[0]["id"] if results else None

    async def _find_movie(self, imdb_id: str) -> int | None:
        results = (await self.tmdb.find(imdb_id, ExternalSource.IMDB)).get("movie_results") or []
        return results[0]["id"] if results else None

    async def _find_episode(self, tvdb_episode_id: int) -> tuple[int, int, int] | None:
        if tvdb_episode_id not in self.found_episodes:
            try:
                result = await self.tmdb.find(str(tvdb_episode_id), ExternalSource.TVDB)
            except TMDBError:
                return None
            episodes = result.get("tv_episode_results") or []
            self.found_episodes[tvdb_episode_id] = (
                (episodes[0]["show_id"], episodes[0]["season_number"], episodes[0]["episode_number"])
                if episodes
                else None
            )
        return self.found_episodes[tvdb_episode_id]

    async def _episodes(self, media: Media) -> dict[tuple[int, int], Episode]:
        if media.id not in self.episodes:
            episodes = await self.session.scalars(sa.select(Episode).filter_by(media_id=media.id))
            self.episodes[media.id] = {(episode.season_number, episode.episode_number): episode for episode in episodes}
        return self.episodes[media.id]
