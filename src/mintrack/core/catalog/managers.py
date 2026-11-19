import collections.abc
import dataclasses
import datetime as dt
import itertools
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import (
    Episode,
    EpisodeRating,
    Media,
    MediaType,
    Season,
    TrackingStatus,
    User,
    UserMedia,
    WatchedEpisode,
)
from mintrack.integrations.tmdb.client import TMDBClient
from mintrack.integrations.tmdb.schemas import TMDBMovie, TMDBSearchResult, TMDBShow
from mintrack.worker.defer import defer_refresh

type Rows = collections.abc.Sequence[collections.abc.Mapping[str, object]]

# TMDB statuses of shows that will not air new episodes.
ENDED_STATUSES = frozenset({"Ended", "Canceled"})
AIRING_MAX_AGE = dt.timedelta(days=1)
MAX_AGE = dt.timedelta(days=7)
# A movie released this recently, or not yet, refreshes daily like an airing show: its digital release dates are
# usually announced in the months after the theatrical release.
RECENT_MOVIE = dt.timedelta(days=180)
# Rows per INSERT, well under PostgreSQL's 65,535 parameters per statement.
INSERT_BATCH = 1000


def is_airing(media: Media) -> bool:
    return media.media_type is MediaType.TV and media.tmdb_status not in ENDED_STATUSES


def episode_code(season_number: int, episode_number: int) -> str:
    """An episode's number as shows are usually labelled: S01E05."""
    return f"S{season_number:02}E{episode_number:02}"


def is_stale(media: Media, now: dt.datetime, language: str) -> bool:
    """Past its refresh period, or fetched in another language than the one configured now."""
    if media.language != language:
        return True
    return now - media.refreshed_at > (AIRING_MAX_AGE if refreshes_daily(media, now) else MAX_AGE)


def refreshes_daily(media: Media, now: dt.datetime) -> bool:
    """An airing show, or a movie released recently or not yet; `CatalogManager.stale_tracked` says the same in SQL,
    and a test checks they agree."""
    if media.media_type is MediaType.TV:
        return is_airing(media)
    return media.release_date is None or media.release_date > (now - RECENT_MOVIE).date()


async def find_media(session: AsyncSession, media_type: MediaType, tmdb_id: int) -> Media | None:
    """The cached media, without asking TMDB."""
    return await session.scalar(sa.select(Media).where(Media.media_type == media_type, Media.tmdb_id == tmdb_id))


@dataclasses.dataclass(frozen=True)
class SearchHit:
    result: TMDBSearchResult
    tracking_status: TrackingStatus | None


class CatalogManager:
    """Movies and shows from TMDB, cached in PostgreSQL."""

    def __init__(self, session: AsyncSession, tmdb: TMDBClient) -> None:
        self.session = session
        self.tmdb = tmdb

    async def search(self, user: User, query: str, media_type: MediaType | None = None) -> list[SearchHit]:
        """TMDB's first page of results, of that type or both, with the user's status of those in their library."""
        return await self._with_statuses(user, await self.tmdb.search(query, media_type))

    async def trending(self, user: User, media_type: MediaType, now: dt.datetime) -> list[SearchHit]:
        """The week's trending shows or movies on TMDB, with the user's status of those in their library."""
        return await self._with_statuses(user, await self.tmdb.trending(media_type, now))

    async def _with_statuses(self, user: User, results: list[TMDBSearchResult]) -> list[SearchHit]:
        statuses = {}
        if results:
            rows = await self.session.execute(
                sa.select(Media.media_type, Media.tmdb_id, UserMedia.status)
                .join(UserMedia, UserMedia.media_id == Media.id)
                .where(
                    UserMedia.user_id == user.id,
                    sa.tuple_(Media.media_type, Media.tmdb_id).in_([(r.media_type, r.id) for r in results]),
                )
            )
            statuses = {(media_type, tmdb_id): status for media_type, tmdb_id, status in rows}
        return [SearchHit(result, statuses.get((result.media_type, result.id))) for result in results]

    async def get_or_fetch(self, media_type: MediaType, tmdb_id: int, now: dt.datetime) -> Media:
        """The cached media, fetched from TMDB on its first request; a stale one gets a refresh deferred in the
        session's transaction."""
        if media := await find_media(self.session, media_type, tmdb_id):
            if self.tmdb.configured and is_stale(media, now, self.tmdb.language):
                await defer_refresh(self.session, media.id)
            return media
        # Ends the read transaction, so no pooled connection waits on TMDB.
        await self.session.commit()
        return await self.fetch(media_type, tmdb_id, now)

    async def fetch(self, media_type: MediaType, tmdb_id: int, now: dt.datetime) -> Media:
        """Fetch from TMDB, then store; call it outside a transaction."""
        if media_type is MediaType.MOVIE:
            return await self._store_movie(await self.tmdb.movie(tmdb_id), now)
        return await self._store_show(await self.tmdb.show(tmdb_id), now)

    async def stale_tracked(self, now: dt.datetime) -> list[uuid.UUID]:
        """Media someone tracks whose metadata is older than its refresh period, or in another language.

        The daily period is `refreshes_daily`'s, plus the movies someone keeps to watch later without a digital
        release date yet, so a late date is still announced within the notification window.
        """
        tracked = sa.exists().where(UserMedia.media_id == Media.id)
        awaited = sa.and_(
            Media.digital_release_date.is_(None),
            sa.exists().where(UserMedia.media_id == Media.id, UserMedia.status == TrackingStatus.WATCH_LATER),
        )
        daily = sa.or_(
            sa.and_(
                Media.media_type == MediaType.TV,
                sa.or_(Media.tmdb_status.is_(None), Media.tmdb_status.not_in(ENDED_STATUSES)),
            ),
            sa.and_(
                Media.media_type == MediaType.MOVIE,
                sa.or_(Media.release_date.is_(None), Media.release_date > (now - RECENT_MOVIE).date(), awaited),
            ),
        )
        stale = sa.or_(
            Media.language.is_distinct_from(self.tmdb.language),
            Media.refreshed_at < now - MAX_AGE,
            sa.and_(daily, Media.refreshed_at < now - AIRING_MAX_AGE),
        )
        return list(await self.session.scalars(sa.select(Media.id).where(tracked, stale).order_by(Media.refreshed_at)))

    async def _upsert_media(self, media_type: MediaType, tmdb_id: int, values: dict[str, object]) -> Media:
        statement = (
            insert(Media)
            .values(media_type=media_type, tmdb_id=tmdb_id, **values)
            .on_conflict_do_update(index_elements=[Media.media_type, Media.tmdb_id], set_=values)
            .returning(Media)
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(statement)).one()

    async def _store_movie(self, movie: TMDBMovie, now: dt.datetime) -> Media:
        return await self._upsert_media(
            MediaType.MOVIE,
            movie.id,
            {
                "title": movie.title,
                "overview": movie.overview,
                "poster_path": movie.poster_path,
                "backdrop_path": movie.backdrop_path,
                "runtime": movie.runtime or None,
                "release_date": movie.release_date,
                "digital_release_date": movie.digital_release_date(),
                "tmdb_status": movie.status,
                "refreshed_at": now,
                "language": self.tmdb.language,
                "vote_average": movie.vote_average,
                "vote_count": movie.vote_count,
            },
        )

    async def _store_show(self, show: TMDBShow, now: dt.datetime) -> Media:
        media = await self._upsert_media(
            MediaType.TV,
            show.id,
            {
                "title": show.name,
                "overview": show.overview,
                "poster_path": show.poster_path,
                "backdrop_path": show.backdrop_path,
                "network": show.networks[0].name if show.networks else None,
                "release_date": show.first_air_date,
                "tmdb_status": show.status,
                "tvdb_id": show.external_ids.tvdb_id,
                "refreshed_at": now,
                "language": self.tmdb.language,
                "vote_average": show.vote_average,
                "vote_count": show.vote_count,
            },
        )
        seasons = [
            {"media_id": media.id, "season_number": season.season_number, "title": season.name}
            for season in show.seasons
        ]
        episodes = [
            {
                "media_id": media.id,
                "season_number": season.season_number,
                "episode_number": episode.episode_number,
                "title": episode.name,
                "air_date": episode.air_date,
                "overview": episode.overview,
                "still_path": episode.still_path,
                "vote_average": episode.vote_average,
                "vote_count": episode.vote_count,
            }
            for season in show.seasons
            for episode in season.episodes
        ]
        await self._upsert(Season, seasons, keys=("media_id", "season_number"), updated=("title",))
        await self._upsert(
            Episode,
            episodes,
            keys=("media_id", "season_number", "episode_number"),
            updated=("title", "air_date", "overview", "still_path", "vote_average", "vote_count"),
        )
        await self._delete_dropped(media, seasons, episodes)
        return media

    async def _upsert(
        self,
        model: type[Season | Episode],
        rows: Rows,
        *,
        keys: tuple[str, ...],
        updated: tuple[str, ...],
    ) -> None:
        for batch in itertools.batched(rows, INSERT_BATCH, strict=False):
            statement = insert(model).values(batch)
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=keys, set_={name: statement.excluded[name] for name in updated}
                )
            )

    async def _delete_dropped(self, media: Media, seasons: Rows, episodes: Rows) -> None:
        """Delete what TMDB no longer lists, except the episodes someone watched or rated and their seasons."""
        listed = sa.select(
            sa.func.unnest(sa.bindparam("seasons", [e["season_number"] for e in episodes], type_=ARRAY(sa.Integer))),
            sa.func.unnest(sa.bindparam("numbers", [e["episode_number"] for e in episodes], type_=ARRAY(sa.Integer))),
        )
        await self.session.execute(
            sa.delete(Episode).where(
                Episode.media_id == media.id,
                sa.tuple_(Episode.season_number, Episode.episode_number).not_in(listed),
                ~sa.exists().where(WatchedEpisode.episode_id == Episode.id),
                ~sa.exists().where(EpisodeRating.episode_id == Episode.id),
            )
        )
        await self.session.execute(
            sa.delete(Season).where(
                Season.media_id == media.id,
                Season.season_number.not_in([season["season_number"] for season in seasons]),
                ~sa.exists().where(Episode.media_id == media.id, Episode.season_number == Season.season_number),
            )
        )
