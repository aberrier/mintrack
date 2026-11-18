import collections.abc
import csv
import dataclasses
import datetime as dt
import enum
import io
import pathlib
import zipfile
import zlib
import zoneinfo

# Upper bound of an uploaded file, and of each file read from a TV Time archive.
MAX_IMPORT_BYTES = 20 * 1024 * 1024

MAX_IMPORT_ROWS = 200_000
# Dates before this year are placeholders.
MIN_YEAR = 1800

# The files of a TV Time GDPR export that hold the tracking history.
TVTIME_FILES = ("tracking-prod-records-v2.csv", "tracking-prod-records.csv")

# A TV Time show row: followed, archived (stopped), or put aside for later.
TVTIME_SHOW_FLAGS = ("is_followed", "is_archived", "is_for_later")
# A TV Time tracking file has at least one of these columns.
TVTIME_COLUMNS = {"key", "episode_id", "movie_name"}
YAMTRACK_COLUMNS = {
    "media_id",
    "source",
    "media_type",
    "title",
    "season_number",
    "episode_number",
    "status",
    "end_date",
}

# Yamtrack statuses that stop a show; a movie is watched only when completed.
YAMTRACK_STOPPED = {"Paused", "Dropped"}
YAMTRACK_COMPLETED = "Completed"


class ImportFileError(ValueError):
    """The uploaded file is not one the chosen source exports."""


class UnmatchedReason(enum.StrEnum):
    UNSUPPORTED = enum.auto()
    NOT_FOUND = enum.auto()
    EPISODE_NOT_FOUND = enum.auto()
    TMDB_UNAVAILABLE = enum.auto()
    # A per-season anime entry matched to a show another season's entry already matched: left to the user.
    TO_CHECK = enum.auto()


@dataclasses.dataclass(frozen=True, kw_only=True)
class ExternalIds:
    tmdb: int | None = None
    tvdb: int | None = None
    imdb: str | None = None
    tvdb_episode: int | None = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class ShowRow:
    title: str
    ids: ExternalIds
    stopped: bool = False
    # Put aside to watch later.
    watch_later: bool = False
    # Episodes watched, in airing order, for sources without episode rows.
    progress: int | None = None
    watched_at: dt.datetime | None = None
    # One season of a show, as MyAnimeList and AniList list anime, matched by title.
    season_entry: bool = False


@dataclasses.dataclass(frozen=True, kw_only=True)
class EpisodeRow:
    title: str
    ids: ExternalIds
    season: int | None
    episode: int | None
    watched_at: dt.datetime | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MovieRow:
    title: str
    ids: ExternalIds
    year: int | None = None
    watched: bool
    watched_at: dt.datetime | None = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class SkippedRow:
    title: str
    reason: UnmatchedReason


type ImportRow = ShowRow | EpisodeRow | MovieRow | SkippedRow


def parse_yamtrack(data: bytes, tz: zoneinfo.ZoneInfo) -> list[ImportRow]:
    """Rows of a Yamtrack CSV export; season rows are left out, their episodes have rows of their own.

    Media from other sources than TMDB (anime from MyAnimeList or AniList, manual entries) are matched by title.
    """
    rows: list[ImportRow] = []
    for row in _read(_decode(data, fallback=None), YAMTRACK_COLUMNS.issubset, "This is not a Yamtrack CSV export."):
        media_type, title = row["media_type"], row["title"].strip()
        if media_type == "season":
            continue
        if media_type not in {"tv", "anime", "episode", "movie"}:
            rows.append(SkippedRow(title=title, reason=UnmatchedReason.UNSUPPORTED))
            continue
        ids = ExternalIds(tmdb=_int(row["media_id"])) if row["source"] == "tmdb" else ExternalIds()
        watched_at = _datetime(row["end_date"], tz) or _datetime(row.get("progressed_at", ""), tz)
        if media_type in {"tv", "anime"}:
            stopped = row["status"] in YAMTRACK_STOPPED
            if media_type == "anime":
                progress = _int(row.get("progress", "")) or None
                rows.append(
                    ShowRow(
                        title=title,
                        ids=ids,
                        stopped=stopped,
                        progress=progress,
                        watched_at=watched_at,
                        season_entry=row["source"] != "tmdb",
                    )
                )
            else:
                rows.append(ShowRow(title=title, ids=ids, stopped=stopped))
        elif media_type == "episode":
            season, episode = _int(row["season_number"]), _int(row["episode_number"])
            rows.append(EpisodeRow(title=title, ids=ids, season=season, episode=episode, watched_at=watched_at))
        else:
            watched = row["status"] == YAMTRACK_COMPLETED
            rows.append(MovieRow(title=title, ids=ids, watched=watched, watched_at=watched_at if watched else None))
    return rows


def parse_tvtime(data: bytes, tz: zoneinfo.ZoneInfo) -> list[ImportRow]:
    """Rows of a TV Time GDPR export: the export's .zip, or one of its tracking CSV files."""
    rows: list[ImportRow] = []
    read = 0
    for content in _tvtime_files(data).values():
        records = _read(
            _decode(content, fallback="latin-1"),
            lambda header: bool(header & TVTIME_COLUMNS),
            "This is not a TV Time tracking file.",
            read_before=read,
        )
        for record in records:
            read += 1
            if (row := _tvtime_row(record, tz)) is not None:
                rows.append(row)
    return rows


def keep_tvtime_tracking_files(data: bytes) -> bytes:
    """The upload reduced to the tracking files when it is the whole export archive."""
    if not _is_zip(data):
        return data
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in _tvtime_files(data).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _is_zip(data: bytes) -> bool:
    try:
        return zipfile.is_zipfile(io.BytesIO(data))
    except ValueError as error:
        # A zip signature with a corrupt directory.
        msg = "The archive cannot be read."
        raise ImportFileError(msg) from error


def _tvtime_files(data: bytes) -> dict[str, bytes]:
    if not _is_zip(data):
        return {TVTIME_FILES[0]: data}
    files: dict[str, bytes] = {}
    budget = MAX_IMPORT_BYTES
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                name = pathlib.PurePosixPath(info.filename).name
                if name in TVTIME_FILES and budget >= 0:
                    with archive.open(info) as member:
                        files[name] = member.read(budget + 1)
                    budget -= len(files[name])
    # ValueError: a corrupt header; UnicodeDecodeError, one of its kind: a file name in no encoding.
    except (zipfile.BadZipFile, NotImplementedError, EOFError, RuntimeError, ValueError, zlib.error) as error:
        msg = "The archive cannot be read."
        raise ImportFileError(msg) from error
    if not files:
        msg = f"The archive has none of the TV Time files {', '.join(TVTIME_FILES)}."
        raise ImportFileError(msg)
    if budget < 0:
        msg = f"The TV Time files are larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB."
        raise ImportFileError(msg)
    return files


def _tvtime_row(record: dict[str, str], tz: zoneinfo.ZoneInfo) -> ImportRow | None:
    key = record.get("key", "")
    movie_name = (record.get("movie_name") or "").strip()
    series_name = (record.get("series_name") or "").strip()
    show_ids = ExternalIds(tvdb=_int(record.get("s_id", "")))

    if movie_name:
        if (record.get("type") or "").strip().lower() != "watch":
            return None
        release_date = record.get("release_date") or ""
        return MovieRow(
            title=movie_name,
            ids=ExternalIds(imdb=(record.get("imdb_id") or "").strip() or None),
            year=_int(release_date[:4]),
            watched=True,
            watched_at=_datetime(record.get("updated_at") or record.get("created_at") or "", tz),
        )
    if key.startswith("user-series-"):
        followed, archived, for_later = (record.get(name) == "true" for name in TVTIME_SHOW_FLAGS)
        if not (followed or archived or for_later):
            return None
        return ShowRow(title=series_name, ids=show_ids, stopped=archived, watch_later=for_later and not archived)
    if key.startswith(("watch-episode-", "rewatch-episode-")) or (not key and record.get("episode_id")):
        return EpisodeRow(
            title=series_name,
            ids=dataclasses.replace(show_ids, tvdb_episode=_int(record.get("episode_id") or record.get("ep_id") or "")),
            season=_int(record.get("season_number") or record.get("s_no") or ""),
            episode=_int(record.get("episode_number") or record.get("ep_no") or ""),
            watched_at=_datetime(record.get("created_at") or "", tz),
        )
    return None


def _decode(data: bytes, fallback: str | None) -> str:
    """The text, without NUL characters: PostgreSQL text cannot hold them."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        if fallback is None:
            msg = "The file is not UTF-8 text."
            raise ImportFileError(msg) from error
        text = data.decode(fallback)
    return text.replace("\x00", "")


def _read(
    text: str, accepts: collections.abc.Callable[[set[str]], bool], wrong_file: str, *, read_before: int = 0
) -> collections.abc.Iterator[dict[str, str]]:
    """The CSV records, once `accepts` approved its header; MAX_IMPORT_ROWS counts the `read_before` records of the
    import's other files. A quote left open is an error rather than a field running to the end of the file."""
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    try:
        if not accepts(set(reader.fieldnames or ())):
            raise ImportFileError(wrong_file)
        for count, row in enumerate(reader, start=read_before + 1):
            if count > MAX_IMPORT_ROWS:
                msg = f"The file has more than {MAX_IMPORT_ROWS} rows."
                raise ImportFileError(msg)
            yield {name: value or "" for name, value in row.items() if name is not None}
    except csv.Error as error:
        msg = "The file is not a valid CSV file."
        raise ImportFileError(msg) from error


def _int(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def _datetime(value: str, tz: zoneinfo.ZoneInfo) -> dt.datetime | None:
    """An ISO date or datetime; a date alone is midnight in `tz`, a datetime without offset is UTC. A year before
    MIN_YEAR is a placeholder for no date (TV Time writes 0001-01-01)."""
    value = value.strip()
    try:
        if len(value) == len("2024-01-31"):
            parsed = dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), tzinfo=tz)
        else:
            parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.year < MIN_YEAR:
        return None
    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    try:
        # Out of range in UTC (9999-12-31T23:59:59-12:00): no date either.
        parsed.astimezone(dt.UTC)
    except OverflowError:
        return None
    return parsed
