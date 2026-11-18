import typing

import typer

from mintrack.config import get_config
from mintrack.db import alembic

command = typer.Typer(no_args_is_help=True, help="Database migrations.")


@command.command()
def migrate(revision: typing.Annotated[str, typer.Argument(help="Target revision.")] = "heads") -> None:
    """Upgrade the database schema (to the latest revision by default)."""
    alembic.upgrade(get_config().database.url(), revision)


@command.command()
def makemigrations(message: typing.Annotated[str, typer.Argument(help="Short description of the change.")]) -> None:
    """Generate a new revision from the models (development only)."""
    alembic.make_revision(get_config().database.url(), message)
