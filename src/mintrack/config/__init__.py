import functools
import os
import pathlib
import typing

import pydantic
import pydantic_settings
from pydantic.fields import FieldInfo

from mintrack.db.config import DatabaseConfig
from mintrack.observability.config import ObservabilityConfig

from .project import Environment, ProjectConfig
from .security import SecurityConfig
from .server import ServerConfig

ENV_PREFIX = "MINTRACK__"
ENV_NESTED_DELIMITER = "__"
FILE_SUFFIX = "_FILE"
DOCKER_SECRETS_DIR = pathlib.Path("/run/secrets")


class ConfigError(Exception):
    """The configuration cannot be loaded; each problem names the variable to fix, never its value."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def variable_name(location: tuple[int | str, ...]) -> str:
    return ENV_PREFIX + ENV_NESTED_DELIMITER.join(str(part).upper() for part in location)


class FileVariablesSource(pydantic_settings.PydanticBaseSettingsSource):
    """Read `MINTRACK__X__Y_FILE=path` as the value of `MINTRACK__X__Y`.

    A relative path names a Docker secret under /run/secrets. The file content is stripped. A variable set directly
    to a non-empty value wins over its `_FILE` variant.
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[typing.Any, str, bool]:  # noqa: ARG002
        return None, field_name, False  # pragma: no cover

    def __call__(self) -> dict[str, typing.Any]:
        values: dict[str, typing.Any] = {}
        problems: list[str] = []
        environ = {name.upper(): value for name, value in os.environ.items()}
        for name, raw_path in environ.items():
            if not name.startswith(ENV_PREFIX) or not name.endswith(FILE_SUFFIX):
                continue
            if environ.get(name.removesuffix(FILE_SUFFIX)):
                continue
            keys = name.removeprefix(ENV_PREFIX).removesuffix(FILE_SUFFIX).lower().split(ENV_NESTED_DELIMITER)
            path = pathlib.Path(raw_path)
            if not path.is_absolute():
                path = DOCKER_SECRETS_DIR / path
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                problems.append(f"{name}: the file it names is not UTF-8 text")
                continue
            except OSError as error:
                problems.append(f"{name}: cannot read the file it names ({error.strerror})")
                continue
            target = values
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = content
        if problems:
            raise ConfigError(problems)
        return values


class Config(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_prefix=ENV_PREFIX.lower(),
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        hide_input_in_errors=True,
    )

    project: ProjectConfig = ProjectConfig()
    server: ServerConfig = ServerConfig()
    security: SecurityConfig = SecurityConfig()
    # Validated even when no variable is set, so each missing field is reported by its own variable name.
    database: DatabaseConfig = pydantic.Field(default_factory=dict, validate_default=True)
    logging: ObservabilityConfig = ObservabilityConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        # _FILE variants come before the environment so they win over an empty variable.
        return init_settings, FileVariablesSource(settings_cls), env_settings, dotenv_settings

    @pydantic.model_validator(mode="after")
    def _production_requirements(self) -> typing.Self:
        if self.project.environment is Environment.PROD and (problem := self.security.secret_key_problem()):
            msg = f"{variable_name(('security', 'secret_key'))}: {problem}"
            raise ValueError(msg)
        return self


def load_config(*, env_file: str | None = ".env") -> Config:
    try:
        return Config(_env_file=env_file)
    except pydantic.ValidationError as error:
        raise ConfigError(describe_validation_error(error)) from None


def describe_validation_error(error: pydantic.ValidationError) -> list[str]:
    problems = []
    for detail in error.errors(include_url=False, include_context=False):
        message = detail["msg"].removeprefix("Value error, ")
        location = detail["loc"]
        problems.append(f"{variable_name(location)}: {message}" if location else message)
    return problems


@functools.cache
def get_config() -> Config:
    return load_config()


__all__ = [
    "Config",
    "ConfigError",
    "DatabaseConfig",
    "Environment",
    "ObservabilityConfig",
    "ProjectConfig",
    "SecurityConfig",
    "ServerConfig",
    "get_config",
    "load_config",
]
