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
    release_date: OptionalDate = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("release_date", "first_air_date")
    )
    poster_path: str | None = None


class TMDBMovie(TMDBModel):
    id: int
    title: str
    overview: Text = ""
    poster_path: str | None = None
    release_date: OptionalDate = None
    status: str | None = None


class TMDBEpisode(TMDBModel):
    season_number: int
    episode_number: int
    name: Text = ""
    air_date: OptionalDate = None


class TMDBSeason(TMDBModel):
    season_number: int
    name: Text = ""
    episodes: list[TMDBEpisode] = []


class TMDBExternalIds(TMDBModel):
    tvdb_id: int | None = None


class TMDBShow(TMDBModel):
    id: int
    name: str
    overview: Text = ""
    poster_path: str | None = None
    first_air_date: OptionalDate = None
    status: str | None = None
    external_ids: TMDBExternalIds = TMDBExternalIds()
    seasons: list[TMDBSeason] = []
