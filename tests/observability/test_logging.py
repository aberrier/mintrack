import collections.abc
import logging

import pytest

from mintrack.config import ObservabilityConfig, get_config
from mintrack.observability.config import LogFormat
from mintrack.observability.logging import configure_logging

SECRET = "mt_secret-value-held-by-a-failing-frame"


@pytest.fixture
def restore_logging() -> collections.abc.Generator[None]:
    yield
    configure_logging(get_config().logging)


@pytest.mark.parametrize("log_format", list(LogFormat))
def test_tracebacks_never_show_frame_locals(
    log_format: LogFormat, capsys: pytest.CaptureFixture[str], restore_logging: None
) -> None:
    configure_logging(ObservabilityConfig(format=log_format))

    def verify(token: str) -> None:
        msg = "database unavailable"
        raise RuntimeError(msg)

    try:
        verify(SECRET)
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("request failed")

    output = capsys.readouterr().err
    assert "database unavailable" in output
    assert SECRET not in output
