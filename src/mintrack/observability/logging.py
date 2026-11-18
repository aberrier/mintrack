import logging
import logging.config
import typing

import structlog

from .config import LogFormat, LogLevel, ObservabilityConfig

logger = structlog.get_logger("mintrack")

# Shared by structlog and stdlib records. The timestamp is added by the formatter, so a record's message is the same
# for every occurrence of an event.
_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.StackInfoRenderer(),
]


def _renderers(log_format: LogFormat) -> list[structlog.typing.Processor]:
    if log_format is LogFormat.CONSOLE:
        return [structlog.dev.ConsoleRenderer()]
    return [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]


def logging_config(log_config: ObservabilityConfig) -> dict[str, typing.Any]:
    """The stdlib logging configuration, also handed to uvicorn so its logs share our format."""
    level = log_config.level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.TimeStamper(fmt="iso"),
                    *_renderers(log_config.format),
                ],
                "foreign_pre_chain": _SHARED_PROCESSORS,
            },
        },
        "handlers": {
            "default": {"class": "logging.StreamHandler", "formatter": "default", "level": level},
        },
        "loggers": {
            "": {"handlers": ["default"], "level": level},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": level, "propagate": False},
        },
    }


def configure_logging(log_config: ObservabilityConfig) -> None:
    """Route structlog through stdlib logging, so uvicorn, Alembic and our own records share one format and our
    errors reach Sentry's logging integration."""
    logging.config.dictConfig(logging_config(log_config))

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    level = log_config.level.upper()
    logging.getLogger("alembic").setLevel(level)
    # Hides the plugin list Alembic logs at INFO on every command.
    logging.getLogger("alembic.runtime.plugins").setLevel(max(logging.WARNING, logging.getLevelNamesMapping()[level]))
    # Their INFO records hold request URLs, whose query holds the TMDB key.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(max(logging.WARNING, logging.getLevelNamesMapping()[level]))
    if log_config.level is LogLevel.DEBUG:
        # INFO logs SQL statements; DEBUG would also log every fetched row.
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
