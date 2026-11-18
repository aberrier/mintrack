import datetime as dt
import zoneinfo

import pytest

from mintrack.core.tracking.statuses import EpisodeProgress, is_aired, show_status
from mintrack.db.models import TrackingStatus

AIRED_WATCHED = EpisodeProgress(aired=True, upcoming=False, watched=True)
AIRED_UNWATCHED = EpisodeProgress(aired=True, upcoming=False, watched=False)
UPCOMING = EpisodeProgress(aired=False, upcoming=True, watched=False)
UNDATED = EpisodeProgress(aired=False, upcoming=False, watched=False)
PARIS = zoneinfo.ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    ("current", "episodes", "ended", "expected"),
    [
        (None, [AIRED_UNWATCHED, UPCOMING], False, TrackingStatus.WATCH_LATER),
        (TrackingStatus.WATCHING, [], False, TrackingStatus.WATCH_LATER),
        (None, [AIRED_WATCHED, AIRED_UNWATCHED], False, TrackingStatus.WATCHING),
        (None, [AIRED_WATCHED, UPCOMING], False, TrackingStatus.UP_TO_DATE),
        (None, [AIRED_WATCHED], False, TrackingStatus.UP_TO_DATE),
        (None, [AIRED_WATCHED, UPCOMING], True, TrackingStatus.UP_TO_DATE),
        (TrackingStatus.UP_TO_DATE, [AIRED_WATCHED, AIRED_WATCHED], True, TrackingStatus.FINISHED),
        (None, [AIRED_WATCHED, UNDATED], True, TrackingStatus.FINISHED),
        (None, [AIRED_WATCHED, UNDATED], False, TrackingStatus.UP_TO_DATE),
        (TrackingStatus.STOPPED, [AIRED_WATCHED, AIRED_UNWATCHED], False, TrackingStatus.STOPPED),
        (TrackingStatus.STOPPED, [AIRED_WATCHED], True, TrackingStatus.STOPPED),
    ],
)
def test_show_status_follows_progress_unless_stopped(
    current: TrackingStatus | None,
    episodes: list[EpisodeProgress],
    ended: bool,  # noqa: FBT001
    expected: TrackingStatus,
) -> None:
    assert show_status(current, episodes, ended=ended) is expected


def test_an_episode_airs_at_its_exact_time_when_known() -> None:
    airstamp = dt.datetime(2026, 3, 1, 20, tzinfo=dt.UTC)

    assert not is_aired(dt.date(2026, 3, 1), airstamp, airstamp - dt.timedelta(minutes=1), PARIS)
    assert is_aired(dt.date(2026, 3, 1), airstamp, airstamp, PARIS)


def test_an_episode_without_time_airs_on_its_date_in_the_users_time_zone() -> None:
    # 23:30 UTC on February 28 is already March 1 in Paris.
    now = dt.datetime(2026, 2, 28, 23, 30, tzinfo=dt.UTC)

    assert is_aired(dt.date(2026, 3, 1), None, now, PARIS)
    assert not is_aired(dt.date(2026, 3, 1), None, now, zoneinfo.ZoneInfo("UTC"))
    assert not is_aired(None, None, now, PARIS)
