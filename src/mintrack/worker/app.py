import functools

import procrastinate

from mintrack.config import get_config
from mintrack.db.config import CONNECT_ARGS

from . import tasks

WORKER_DEFAULTS: procrastinate.app.WorkerOptions = {
    # Seconds running jobs get to finish on shutdown, within Docker's 10 s stop timeout.
    "shutdown_graceful_timeout": 5,
    "delete_jobs": "successful",
    # A long import or sync leaves room for the other jobs; one user's imports and syncs still run one at a time
    # (their lock), and so do the jobs of one show.
    "concurrency": 4,
}

# The Procrastinate release whose schema the migrations apply (see db/migrations/procrastinate).
PROCRASTINATE_SCHEMA_VERSION = "3.11.0"


@functools.cache
def get_worker_app() -> procrastinate.App:
    """The Procrastinate app: tasks run by the worker and deferred by the server, on the configured database."""
    database = get_config().database
    connection = {
        "host": database.host,
        "port": database.port,
        "user": database.user,
        "password": database.password.get_secret_value(),
        "dbname": database.name,
        **CONNECT_ARGS,
    }
    if database.sslmode is not None:
        connection["sslmode"] = database.sslmode.value
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(kwargs=connection), worker_defaults=WORKER_DEFAULTS
    )
    app.add_tasks_from(tasks.blueprint, namespace="mintrack")
    return app
