import pydantic
import pytest
import sentry_sdk
from sentry_sdk.types import Event

from mintrack.config import Config, ObservabilityConfig, get_config
from mintrack.observability.sentry import configure_sentry, scrub_event, sentry_options


def config_with_dsn() -> Config:
    logging = ObservabilityConfig(sentry_dsn=pydantic.SecretStr("https://key@sentry.example/1"))
    return get_config().model_copy(update={"logging": logging})


def test_sentry_is_off_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))

    configure_sentry(get_config())

    assert calls == []


def test_sentry_sends_no_personal_data() -> None:
    options = sentry_options(config_with_dsn())

    assert options["dsn"] == "https://key@sentry.example/1"
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["traces_sample_rate"] == 0.0
    assert options["before_send"] is scrub_event
    assert options["before_send_transaction"] is scrub_event
    assert options["environment"] == "pytest"


def test_events_lose_credentials_query_strings_and_bodies() -> None:
    event: Event = {
        "request": {
            "url": "https://mintrack.test/invite?token=abc",
            "query_string": "token=abc",
            "cookies": {"session": "abc"},
            "data": {"password": "hunter2"},
            "headers": {
                "Cookie": "session=abc",
                "Authorization": "Bearer abc",
                "X-XSRF-TOKEN": "abc",
                "User-Agent": "Firefox",
            },
        }
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed == {"request": {"url": "https://mintrack.test/invite", "headers": {"User-Agent": "Firefox"}}}


@pytest.mark.parametrize(
    ("category", "kept"),
    [("uvicorn.access", False), ("sqlalchemy.engine.Engine", False), ("mintrack", True), ("uvicorn.error", True)],
)
def test_breadcrumbs_from_access_and_sql_logs_are_dropped(category: str, *, kept: bool) -> None:
    options = sentry_options(config_with_dsn())
    crumb = {"category": category, "message": '203.0.113.7:0 - "GET /api/x?token=abc HTTP/1.1" 500'}

    assert (options["before_breadcrumb"](crumb, {}) is not None) is kept


def test_the_release_names_the_commit_of_the_image() -> None:
    config = config_with_dsn()
    project = config.project.model_copy(update={"commit": "abc1234"})

    assert sentry_options(config.model_copy(update={"project": project}))["release"].endswith("+abc1234")
    assert "+" not in sentry_options(config)["release"]
