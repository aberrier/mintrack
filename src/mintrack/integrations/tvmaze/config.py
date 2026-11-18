import pydantic


class TvmazeConfig(pydantic.BaseModel):
    url: pydantic.AnyHttpUrl = pydantic.AnyHttpUrl("https://api.tvmaze.com")
