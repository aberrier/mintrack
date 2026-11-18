import enum

import pydantic


class LogFormat(enum.StrEnum):
    CONSOLE = enum.auto()
    JSON = enum.auto()


class LogLevel(enum.StrEnum):
    DEBUG = enum.auto()
    INFO = enum.auto()
    WARNING = enum.auto()
    ERROR = enum.auto()
    CRITICAL = enum.auto()


class ObservabilityConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    format: LogFormat = LogFormat.CONSOLE
    level: LogLevel = LogLevel.INFO

    # Sentry stays off unless a DSN is set.
    sentry_dsn: pydantic.SecretStr | None = None
    sentry_traces_sample_rate: float = pydantic.Field(default=0.0, ge=0.0, le=1.0)
