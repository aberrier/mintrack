import pydantic


class TMDBConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    # The API key (v3 auth) from https://www.themoviedb.org/settings/api.
    api_key: pydantic.SecretStr | None = None
    # Language of titles and overviews, such as en, fr or pt-BR.
    language: str = "en"
    url: pydantic.AnyHttpUrl = pydantic.AnyHttpUrl("https://api.themoviedb.org/3")

    @pydantic.field_validator("api_key", mode="before")
    @classmethod
    def _empty_as_unset(cls, value: object) -> object:
        return value or None
