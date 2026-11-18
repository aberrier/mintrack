import datetime as dt
import typing

from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.db.models import Episode, Media, MediaType
from mintrack.integrations.tmdb.client import TMDBClient, TMDBError, TMDBNotFoundError
from mintrack.integrations.tmdb.config import TMDBConfig

SHOW_TMDB_ID, SHOW_TVDB_ID, SHOW_TITLE = 1001, 5001, "Northern Lights"
MOVIE_TMDB_ID, MOVIE_IMDB_ID, MOVIE_TITLE = 2001, "tt0000001", "Glass Harbor"
# TVDB ids of the show's episodes, by (season, episode).
TVDB_EPISODE_IDS = {(1, 1): 9011, (1, 2): 9012, (1, 3): 9013, (2, 1): 9021}


class FakeTMDB(TMDBClient):
    """TMDB's /find and /search answers for the one show and the one movie of `seed_catalogue`."""

    def __init__(self, *, down: bool = False) -> None:
        super().__init__(TMDBConfig(api_key="test-key"))
        self.down = down
        self.calls = 0

    async def _get(self, path: str, **params: str | int) -> dict[str, typing.Any]:
        self.calls += 1
        if self.down:
            raise TMDBError
        if path.startswith(("movie/", "tv/")):
            # Only the seeded media are known, and they are already cached.
            raise TMDBNotFoundError(path)
        if path == "search/multi":
            results = [
                {"id": SHOW_TMDB_ID, "media_type": "tv", "name": SHOW_TITLE, "first_air_date": "2019-01-01"},
                {"id": MOVIE_TMDB_ID, "media_type": "movie", "title": MOVIE_TITLE, "release_date": "2020-05-01"},
                {"id": 1, "media_type": "person", "name": SHOW_TITLE},
            ]
            return {
                "results": [
                    result for result in results if params["query"] in {result.get("title"), result.get("name")}
                ]
            }
        external_id = path.removeprefix("find/")
        if external_id == MOVIE_IMDB_ID:
            return {"movie_results": [{"id": MOVIE_TMDB_ID}]}
        if external_id == str(SHOW_TVDB_ID):
            return {"tv_results": [{"id": SHOW_TMDB_ID}]}
        return {
            "tv_episode_results": [
                {"show_id": SHOW_TMDB_ID, "season_number": season, "episode_number": number}
                for (season, number), tvdb_id in TVDB_EPISODE_IDS.items()
                if str(tvdb_id) == external_id
            ]
        }


async def seed_catalogue(session: AsyncSession) -> tuple[Media, Media]:
    """The show and the movie, cached as if fetched from TMDB; every episode has aired."""
    now = dt.datetime.now(dt.UTC)
    show = Media(
        tmdb_id=SHOW_TMDB_ID, media_type=MediaType.TV, title=SHOW_TITLE, tvdb_id=SHOW_TVDB_ID, refreshed_at=now
    )
    movie = Media(tmdb_id=MOVIE_TMDB_ID, media_type=MediaType.MOVIE, title=MOVIE_TITLE, refreshed_at=now)
    session.add_all([show, movie])
    await session.flush()
    session.add_all(
        Episode(
            media_id=show.id,
            season_number=season,
            episode_number=number,
            title=f"Episode {season}x{number}",
            air_date=dt.date(2019, season, number),
        )
        for season, number in TVDB_EPISODE_IDS
    )
    await session.flush()
    return show, movie
