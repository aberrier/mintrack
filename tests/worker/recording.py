import collections.abc
import contextlib


class RecordingWorkerApp:
    """Stands for the Procrastinate app where only whether a worker runs matters."""

    def __init__(self) -> None:
        self.runs: list[str] = []

    def run_worker(self) -> None:
        self.runs.append("run_worker")

    async def run_worker_async(self, **_: object) -> None:
        self.runs.append("run_worker_async")

    @contextlib.asynccontextmanager
    async def open_async(self) -> collections.abc.AsyncGenerator[None]:
        yield
