import datetime as dt
import io
import zipfile
import zoneinfo

import pytest

from mintrack.core.imports import parsers
from mintrack.core.imports.parsers import (
    EpisodeRow,
    ExternalIds,
    ImportFileError,
    MovieRow,
    ShowRow,
    SkippedRow,
    UnmatchedReason,
    parse_tvtime,
    parse_yamtrack,
)

PARIS = zoneinfo.ZoneInfo("Europe/Paris")
UTC = zoneinfo.ZoneInfo("UTC")

YAMTRACK_HEADER = (
    '"media_id","source","media_type","title","image","season_number","episode_number","score","progress",'
    '"status","start_date","end_date","notes","progressed_at"'
)


def yamtrack_csv(*rows: str) -> bytes:
    return "\n".join([YAMTRACK_HEADER, *rows]).encode()


def test_yamtrack_rows_keep_ids_dates_and_statuses() -> None:
    data = yamtrack_csv(
        '"1001","tmdb","tv","Northern Lights","","","","","2","In progress","","","",""',
        '"1001","tmdb","season","Northern Lights","","1","","","2","Completed","","","",""',
        '"1001","tmdb","episode","Northern Lights","","1","2","","","","","2024-02-09","",""',
        '"1001","tmdb","episode","Northern Lights","","1","3","","","","","2024-02-10T21:30:00Z","",""',
        '"1001","tmdb","episode","Northern Lights","","2","1","","","","","","",""',
        '"2001","tmdb","movie","Glass Harbor","","","","9","1","Completed","","","","2024-03-01T20:00:00+00:00"',
        '"2002","tmdb","movie","Later Movie","","","","","0","Planning","","","","2024-03-02T20:00:00Z"',
    )

    rows = parse_yamtrack(data, PARIS)

    show_ids = ExternalIds(tmdb=1001)
    assert rows == [
        ShowRow(title="Northern Lights", ids=show_ids),
        EpisodeRow(
            title="Northern Lights",
            ids=show_ids,
            season=1,
            episode=2,
            watched_at=dt.datetime(2024, 2, 9, tzinfo=PARIS),
        ),
        EpisodeRow(
            title="Northern Lights",
            ids=show_ids,
            season=1,
            episode=3,
            watched_at=dt.datetime(2024, 2, 10, 21, 30, tzinfo=dt.UTC),
        ),
        EpisodeRow(title="Northern Lights", ids=show_ids, season=2, episode=1, watched_at=None),
        MovieRow(
            title="Glass Harbor",
            ids=ExternalIds(tmdb=2001),
            watched=True,
            watched_at=dt.datetime(2024, 3, 1, 20, tzinfo=dt.UTC),
        ),
        MovieRow(title="Later Movie", ids=ExternalIds(tmdb=2002), watched=False),
    ]


@pytest.mark.parametrize(
    ("status", "stopped", "watched"),
    [
        ("Planning", False, False),
        ("In progress", False, False),
        ("Paused", True, False),
        ("Completed", False, True),
        ("Dropped", True, False),
    ],
)
def test_yamtrack_statuses_stop_shows_and_mark_movies_watched(status: str, *, stopped: bool, watched: bool) -> None:
    data = yamtrack_csv(
        f'"1","tmdb","tv","Show","","","","","","{status}","","","",""',
        f'"2","tmdb","movie","Movie","","","","","","{status}","","2024-01-01","",""',
    )

    show, movie = parse_yamtrack(data, UTC)

    assert isinstance(show, ShowRow)
    assert isinstance(movie, MovieRow)
    assert (show.stopped, movie.watched) == (stopped, watched)


def test_yamtrack_media_from_other_sources_keep_only_their_title() -> None:
    data = yamtrack_csv(
        '"52991","mal","anime","Some Anime","","","","","3","Paused","","2024-05-01","",""',
        '"7","manual","movie","Home Video","","","","","","Completed","","2024-01-01","",""',
        '"1942","igdb","game","Some Game","","","","","","Completed","","","",""',
    )

    assert parse_yamtrack(data, UTC) == [
        ShowRow(
            title="Some Anime",
            ids=ExternalIds(),
            stopped=True,
            progress=3,
            season_entry=True,
            watched_at=dt.datetime(2024, 5, 1, tzinfo=UTC),
        ),
        MovieRow(
            title="Home Video",
            ids=ExternalIds(),
            watched=True,
            watched_at=dt.datetime(2024, 1, 1, tzinfo=UTC),
        ),
        SkippedRow(title="Some Game", reason=UnmatchedReason.UNSUPPORTED),
    ]


def test_files_over_the_row_limit_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers, "MAX_IMPORT_ROWS", 1)
    data = yamtrack_csv(*['"1","tmdb","tv","Show","","","","","","Planning","","","",""'] * 2)

    with pytest.raises(ImportFileError, match="more than 1 rows"):
        parse_yamtrack(data, UTC)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"title,status\nShow,Completed\n", id="other CSV"),
        pytest.param(b"\xff\xfe\x00not text", id="not UTF-8"),
        pytest.param(b"", id="empty"),
    ],
)
def test_yamtrack_rejects_other_files(data: bytes) -> None:
    with pytest.raises(ImportFileError):
        parse_yamtrack(data, UTC)


TVTIME_V2 = (
    "key,s_id,series_name,is_followed,episode_id,season_number,episode_number,created_at\n"
    "user-series-1-5001,5001,Northern Lights,true,,,,2023-01-01 10:00:00\n"
    "user-series-1-5002,5002,Dropped Show,false,,,,2023-01-01 10:00:00\n"
    "watch-episode-1-9011,5001,Northern Lights,,9011,1,1,2023-01-02 20:00:00\n"
    "rewatch-episode-1-9011,5001,Northern Lights,,9011,1,1,2023-06-02 20:00:00\n"
    "vote-episode-1-9011,5001,Northern Lights,,9011,1,1,2023-01-02 20:05:00\n"
)
TVTIME_RECORDS = (
    "series_name,created_at,episode_id,season_number,episode_number,movie_name,type,updated_at,release_date\n"
    "Northern Lights,2023-01-03 21:00:00,9012,1,2,,,,\n"
    ",,,,,Glass Harbor,watch,2023-02-01 22:00:00,2020-05-01\n"
    ",,,,,Glass Harbor,follow,2023-01-15 10:00:00,2020-05-01\n"
)


def test_tvtime_v2_rows_use_the_tvdb_ids() -> None:
    rows = parse_tvtime(TVTIME_V2.encode(), UTC)

    ids = ExternalIds(tvdb=5001, tvdb_episode=9011)
    assert rows == [
        ShowRow(title="Northern Lights", ids=ExternalIds(tvdb=5001)),
        EpisodeRow(
            title="Northern Lights", ids=ids, season=1, episode=1, watched_at=dt.datetime(2023, 1, 2, 20, tzinfo=dt.UTC)
        ),
        EpisodeRow(
            title="Northern Lights", ids=ids, season=1, episode=1, watched_at=dt.datetime(2023, 6, 2, 20, tzinfo=dt.UTC)
        ),
    ]


def test_tvtime_short_column_names_are_read() -> None:
    data = (
        b"key,s_id,series_name,ep_id,s_no,ep_no,created_at"
        + bytes([10])
        + b"watch-episode-1,5001,Northern Lights,9012,1,2,2023-01-03 21:00:00"
    )

    assert parse_tvtime(data, UTC) == [
        EpisodeRow(
            title="Northern Lights",
            ids=ExternalIds(tvdb=5001, tvdb_episode=9012),
            season=1,
            episode=2,
            watched_at=dt.datetime(2023, 1, 3, 21, tzinfo=dt.UTC),
        )
    ]


def test_tvtime_records_rows_carry_episode_ids_and_movie_titles() -> None:
    rows = parse_tvtime(TVTIME_RECORDS.encode(), UTC)

    assert rows == [
        EpisodeRow(
            title="Northern Lights",
            ids=ExternalIds(tvdb_episode=9012),
            season=1,
            episode=2,
            watched_at=dt.datetime(2023, 1, 3, 21, tzinfo=dt.UTC),
        ),
        MovieRow(
            title="Glass Harbor",
            ids=ExternalIds(),
            year=2020,
            watched=True,
            watched_at=dt.datetime(2023, 2, 1, 22, tzinfo=dt.UTC),
        ),
    ]


def tvtime_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_tvtime_export_archive_reads_both_tracking_files() -> None:
    data = tvtime_zip(
        {
            "export/tracking-prod-records-v2.csv": TVTIME_V2,
            "export/tracking-prod-records.csv": TVTIME_RECORDS,
            "export/user.csv": "name\nsomeone\n",
        }
    )

    assert parse_tvtime(data, UTC) == parse_tvtime(TVTIME_V2.encode(), UTC) + parse_tvtime(TVTIME_RECORDS.encode(), UTC)


def test_only_the_tracking_files_of_a_tvtime_archive_are_kept() -> None:
    data = tvtime_zip({"export/tracking-prod-records-v2.csv": TVTIME_V2, "export/user.csv": "name\nsomeone\n"})

    with zipfile.ZipFile(io.BytesIO(parsers.keep_tvtime_tracking_files(data))) as archive:
        assert {info.filename: archive.read(info).decode() for info in archive.infolist()} == {
            "tracking-prod-records-v2.csv": TVTIME_V2
        }


def test_tvtime_archive_over_the_size_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = tvtime_zip({"tracking-prod-records-v2.csv": TVTIME_V2, "tracking-prod-records.csv": TVTIME_RECORDS})
    monkeypatch.setattr(parsers, "MAX_IMPORT_BYTES", len(TVTIME_V2) + 10)

    with pytest.raises(ImportFileError, match="larger than"):
        parse_tvtime(data, UTC)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(tvtime_zip({"user.csv": "name\nsomeone\n"}), id="archive without tracking files"),
        pytest.param(b"title,year\nMovie,2020\n", id="other CSV"),
        pytest.param(b"PK\x03\x04broken", id="broken archive"),
    ],
)
def test_tvtime_rejects_other_files(data: bytes) -> None:
    with pytest.raises(ImportFileError):
        parse_tvtime(data, UTC)


def test_a_corrupt_archive_is_an_import_error_and_never_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    # A file name flagged UTF-8 that is not.
    bad_name = tvtime_zip({"é.csv": "x"}).replace("é".encode(), b"\xff\xfe")
    with pytest.raises(ImportFileError, match="cannot be read"):
        parse_tvtime(bad_name, UTC)

    def corrupt_directory(_: object) -> bool:
        raise ValueError

    monkeypatch.setattr(parsers.zipfile, "is_zipfile", corrupt_directory)
    with pytest.raises(ImportFileError, match="cannot be read"):
        parsers.keep_tvtime_tracking_files(b"PK\x05\x06")


def test_a_quote_left_open_is_rejected_rather_than_swallowing_the_rest() -> None:
    data = yamtrack_csv('"2","tmdb","tv","Unclosed,"","","","","Planning","","","",""', "3,tmdb,tv,Swallowed")

    with pytest.raises(ImportFileError, match="not a valid CSV"):
        parse_yamtrack(data, UTC)


def test_the_row_limit_counts_both_tvtime_files(monkeypatch: pytest.MonkeyPatch) -> None:
    data = tvtime_zip({"tracking-prod-records-v2.csv": TVTIME_V2, "tracking-prod-records.csv": TVTIME_RECORDS})
    monkeypatch.setattr(parsers, "MAX_IMPORT_ROWS", 6)

    with pytest.raises(ImportFileError, match="more than 6 rows"):
        parse_tvtime(data, UTC)


def test_tvtime_archived_shows_are_stopped_and_shows_for_later_put_aside() -> None:
    data = (
        b"key,s_id,series_name,is_followed,is_archived,is_for_later\n"
        b"user-series-1,5001,Archived,false,true,false\n"
        b"user-series-2,5002,Later,false,false,true\n"
        b"user-series-3,5003,Followed,true,false,false\n"
        b"user-series-4,5004,Forgotten,false,false,false\n"
    )

    assert parse_tvtime(data, UTC) == [
        ShowRow(title="Archived", ids=ExternalIds(tvdb=5001), stopped=True),
        ShowRow(title="Later", ids=ExternalIds(tvdb=5002), watch_later=True),
        ShowRow(title="Followed", ids=ExternalIds(tvdb=5003)),
    ]


def test_tvtime_placeholder_dates_and_nul_characters_are_dropped() -> None:
    data = (
        b"key,s_id,series_name,ep_id,s_no,ep_no,created_at"
        + bytes([10])
        + b"watch-episode-1,5001,North\x00ern Lights,9012,1,2,0001-01-01 00:00:00"
    )

    [row] = parse_tvtime(data, UTC)

    assert isinstance(row, EpisodeRow)
    assert (row.title, row.watched_at) == ("Northern Lights", None)
