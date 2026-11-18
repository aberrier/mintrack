import datetime as dt
import itertools
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Episode, Media, MediaType, TrackingStatus, User, UserMedia, WatchedEpisode
from tests.fakes.tmdb import MAX_ID

# Past the fake TMDB's ids.
_tmdb_ids = itertools.count(MAX_ID + 1)

type Schedule = dict[tuple[int, int], dt.date | dt.datetime | None]


async def add_user(session: AsyncSession, *, timezone: str = "UTC") -> User:
    user = User(username=f"user-{uuid.uuid4()}", timezone=timezone)
    session.add(user)
    await session.flush()
    return user


async def add_show(
    session: AsyncSession,
    schedule: Schedule,
    *,
    title: str = "Show",
    tvdb_id: int | None = None,
    tmdb_status: str = "Returning Series",
) -> tuple[Media, dict[tuple[int, int], Episode]]:
    """A show whose episodes air as `schedule` says: a date (TMDB only), an exact UTC time (TVmaze) or unknown."""
    show = Media(
        media_type=MediaType.TV,
        tmdb_id=next(_tmdb_ids),
        title=title,
        poster_path=f"/{title.lower()}.jpg",
        tmdb_status=tmdb_status,
        tvdb_id=tvdb_id,
        refreshed_at=dt.datetime.now(dt.UTC),
    )
    session.add(show)
    await session.flush()
    episodes = {}
    for (season, number), airs in schedule.items():
        is_exact = isinstance(airs, dt.datetime)
        episode = Episode(
            media_id=show.id,
            season_number=season,
            episode_number=number,
            title=f"Episode {season}x{number}",
            air_date=airs.date() if is_exact else airs,
            airstamp=airs if is_exact else None,
        )
        episodes[season, number] = episode
    session.add_all(episodes.values())
    await session.flush()
    return show, episodes


async def follow(
    session: AsyncSession, user: User, show: Media, status: TrackingStatus, *, at: dt.datetime | None = None
) -> None:
    at = at or dt.datetime.now(dt.UTC)
    session.add(UserMedia(user_id=user.id, media_id=show.id, status=status, added_at=at, updated_at=at))
    await session.flush()


async def watch(session: AsyncSession, user: User, episode: Episode, at: dt.datetime) -> None:
    session.add(WatchedEpisode(user_id=user.id, episode_id=episode.id, watched_at=at))
    await session.flush()
