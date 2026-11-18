import sys

import sentry_sdk
from sqlalchemy.exc import OperationalError

from mintrack.cli.app import get_cli_app
from mintrack.config import ConfigError, get_config
from mintrack.observability.logging import configure_logging
from mintrack.observability.sentry import configure_sentry

CONFIG_ERROR_EXIT_CODE = 2
DATABASE_ERROR_EXIT_CODE = 3


def main() -> None:
    try:
        config = get_config()
    except ConfigError as error:
        # One line per variable to fix, without a traceback or the rejected values.
        sys.stderr.write("MinTrack cannot start, the configuration is invalid:\n")
        sys.stderr.writelines(f"  - {problem}\n" for problem in error.problems)
        raise SystemExit(CONFIG_ERROR_EXIT_CODE) from None

    configure_logging(config.logging)
    configure_sentry(config)

    try:
        get_cli_app()(standalone_mode=True)
    except OperationalError as error:
        # libpq's message names the host and the reason (refused, authentication...), never the password.
        database = config.database
        sys.stderr.write(f"MinTrack cannot reach PostgreSQL at {database.host}:{database.port}: {error.orig}\n")
        raise SystemExit(DATABASE_ERROR_EXIT_CODE) from None
    except Exception:
        # Typer installs its own excepthook, which bypasses Sentry's: report startup crashes explicitly.
        sentry_sdk.capture_exception()
        sentry_sdk.flush()
        raise


if __name__ == "__main__":
    main()
