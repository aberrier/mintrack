import dataclasses
import datetime as dt
import zoneinfo

from mintrack.db.models import TrackingStatus

SPECIALS_SEASON = 0


@dataclasses.dataclass(frozen=True)
class EpisodeProgress:
    """A regular episode (not a special) as the status rules see it. Without a date it is neither aired nor upcoming."""

    aired: bool
    upcoming: bool
    watched: bool


def air_time_known(air_date: dt.date | None, airstamp: dt.datetime | None) -> bool:
    return air_date is not None or airstamp is not None


def is_aired(
    air_date: dt.date | None, airstamp: dt.datetime | None, now: dt.datetime, timezone: zoneinfo.ZoneInfo
) -> bool:
    """Aired at its exact time when known, else on its date in the user's time zone; False without a date."""
    if airstamp is not None:
        return airstamp <= now
    return air_date is not None and air_date <= now.astimezone(timezone).date()


def show_status(current: TrackingStatus | None, episodes: list[EpisodeProgress], *, ended: bool) -> TrackingStatus:
    if current is TrackingStatus.STOPPED:
        return TrackingStatus.STOPPED
    if not any(episode.watched for episode in episodes):
        return TrackingStatus.WATCH_LATER
    if any(episode.aired and not episode.watched for episode in episodes):
        return TrackingStatus.WATCHING
    if ended and not any(episode.upcoming and not episode.watched for episode in episodes):
        return TrackingStatus.FINISHED
    return TrackingStatus.UP_TO_DATE
