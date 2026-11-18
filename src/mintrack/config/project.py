import enum
import importlib.metadata

import pydantic


class Environment(enum.StrEnum):
    DEV = enum.auto()
    PROD = enum.auto()
    PYTEST = enum.auto()


class ProjectConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    name: str = "mintrack"
    version: str = pydantic.Field(default_factory=lambda: importlib.metadata.version("mintrack"))
    commit: str = "unknown"
    environment: Environment = Environment.DEV
    # Only source of the scheme and origin of anything absolute (cookies, links, push subject).
    public_url: pydantic.AnyHttpUrl = pydantic.AnyHttpUrl("http://localhost:8000")

    @pydantic.field_validator("public_url")
    @classmethod
    def _origin_only(cls, value: pydantic.AnyHttpUrl) -> pydantic.AnyHttpUrl:
        if value.path not in {None, "", "/"} or value.query or value.fragment or value.username:
            msg = "must be an origin such as https://mintrack.example.com, without path, query or credentials"
            raise ValueError(msg)
        return value

    @property
    def public_origin(self) -> str:
        return str(self.public_url).removesuffix("/")
