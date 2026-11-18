import typer

from mintrack.worker import get_worker_app

command = typer.Typer(invoke_without_command=True, help="Run the background worker on its own.")


@command.callback()
def main() -> None:
    get_worker_app().run_worker()
