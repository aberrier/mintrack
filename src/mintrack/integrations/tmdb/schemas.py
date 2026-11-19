import datetime as dt
import typing

import pydantic

from mintrack.db.models import MediaType


def _empty_as_none(value: object) -> object:
    return value or None


# TMDB sends "" for an unknown date.
OptionalDate = typing.Annotated[dt.date | None, pydantic.BeforeValidator(_empty_as_none)]
Text = typing.Annotated[str, pydantic.BeforeValidator(lambda value: value or "")]


class TMDBModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)


class TMDBSearchResult(TMDBModel):
    id: int
    media_type: MediaType
    title: str = pydantic.Field(validation_alias=pydantic.AliasChoices("title", "name"))
    original_title: str | None = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("original_title", "original_name")
    )
    release_date: OptionalDate = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("release_date", "first_air_date")
    )
    poster_path: str | None = None


class TMDBReleaseDate(TMDBModel):
    # 1 premiere, 2 limited theatrical, 3 theatrical, 4 digital, 5 physical, 6 TV.
    type: int
    # Missing from some entries: such an entry is skipped rather than failing the whole movie.
    release_date: typing.Annotated[dt.datetime | None, pydantic.BeforeValidator(_empty_as_none)] = None


class TMDBCountryReleases(TMDBModel):
    release_dates: list[TMDBReleaseDate] = []


class TMDBReleaseDates(TMDBModel):
    results: list[TMDBCountryReleases] = []


DIGITAL_RELEASE_TYPE = 4


class TMDBMovie(TMDBModel):
    id: int
    title: str
    overview: Text = ""
    poster_path: str | None = None
    backdrop_path: str | None = None
    runtime: int | None = None
    release_date: OptionalDate = None
    status: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    release_dates: TMDBReleaseDates = TMDBReleaseDates()

    def digital_release_date(self) -> dt.date | None:
        """The first digital release, in any country."""
        dates = [
            release.release_date.date()
            for country in self.release_dates.results
            for release in country.release_dates
            if release.type == DIGITAL_RELEASE_TYPE and release.release_date is not None
        ]
        return min(dates, default=None)


class TMDBEpisode(TMDBModel):
    season_number: int
    episode_number: int
    name: Text = ""
    air_date: OptionalDate = None
    overview: Text = ""
    still_path: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None


class TMDBSeason(TMDBModel):
    season_number: int
    name: Text = ""
    episodes: list[TMDBEpisode] = []


class TMDBExternalIds(TMDBModel):
    tvdb_id: int | None = None


class TMDBNetwork(TMDBModel):
    name: str


class TMDBShow(TMDBModel):
    id: int
    name: str
    overview: Text = ""
    poster_path: str | None = None
    backdrop_path: str | None = None
    networks: list[TMDBNetwork] = []
    first_air_date: OptionalDate = None
    status: str | None = None
    external_ids: TMDBExternalIds = TMDBExternalIds()
    seasons: list[TMDBSeason] = []
    vote_average: float | None = None
    vote_count: int | None = None
