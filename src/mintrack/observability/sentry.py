import typing

import sentry_sdk
from sentry_sdk.types import Breadcrumb, BreadcrumbHint, Event, Hint

from mintrack.config import Config

# Headers that carry credentials.
SENSITIVE_HEADERS = frozenset({"cookie", "set-cookie", "authorization", "x-xsrf-token", "proxy-authorization"})
# Loggers whose records hold client addresses, query strings or SQL parameters.
IGNORED_BREADCRUMB_LOGGERS = frozenset({"uvicorn.access", "sqlalchemy.engine.Engine"})


def scrub_event(event: Event, _hint: Hint) -> Event:
    request = event.get("request")
    if request:
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_HEADERS}
        for key in ("cookies", "query_string", "data"):
            request.pop(key, None)
        if isinstance(url := request.get("url"), str):
            request["url"] = url.split("?", 1)[0]
    return event


def drop_sensitive_breadcrumb(crumb: Breadcrumb, _hint: BreadcrumbHint) -> Breadcrumb | None:
    return None if crumb.get("category") in IGNORED_BREADCRUMB_LOGGERS else crumb


def sentry_options(config: Config) -> dict[str, typing.Any]:
    dsn = config.logging.sentry_dsn
    return {
        "dsn": dsn.get_secret_value() if dsn else None,
        "environment": str(config.project.environment),
        "release": f"{config.project.name}@{config.project.version}",
        "send_default_pii": False,
        "include_local_variables": False,
        "max_request_body_size": "never",
        "traces_sample_rate": config.logging.sentry_traces_sample_rate,
        "before_send": scrub_event,
        "before_send_transaction": scrub_event,
        "before_breadcrumb": drop_sensitive_breadcrumb,
    }


def configure_sentry(config: Config) -> None:
    if config.logging.sentry_dsn is not None:
        sentry_sdk.init(**sentry_options(config))
