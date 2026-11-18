import asyncio
import pathlib
import typing

import typer

from mintrack.config import get_config
from mintrack.core.accounts.managers import AccountManager
from mintrack.core.imports.managers import ImportInProgressError, ImportManager
from mintrack.core.imports.parsers import MAX_IMPORT_BYTES, ImportFileError
from mintrack.db.database import DatabaseManager
from mintrack.db.models import ImportJob, ImportSource, ImportStatus
from mintrack.integrations.tmdb.client import get_tmdb_client

command = typer.Typer(
    invoke_without_command=True,
    help="Import a Yamtrack or TV Time export for a user, as the import card of their profile does.",
)


class ImportFailedError(Exception):
    pass


async def _import(username: str, source: ImportSource, filename: str, data: bytes) -> ImportJob:
    database = DatabaseManager(get_config().database.url())
    try:
        async with database.session() as session:
            user = await AccountManager(session).get_user(username)
            if user is None:
                msg = f"No user named {username}."
                raise ImportFailedError(msg)
            manager = ImportManager(session, get_tmdb_client())
            # The job the worker would run, run here: the command returns once it is done.
            job = await manager.create(user, source, filename, data, queue=False)
            await session.commit()
            await manager.run(job.id)
            await session.refresh(job)
            return job
    finally:
        await database.close()


@command.callback()
def main(
    username: typing.Annotated[str, typer.Argument(help="The user to import for, case-insensitive.")],
    source: typing.Annotated[ImportSource, typer.Argument(help="Where the export comes from.")],
    file: typing.Annotated[
        pathlib.Path, typer.Argument(exists=True, dir_okay=False, help="A Yamtrack CSV, or a TV Time .zip or CSV.")
    ],
) -> None:
    """Import an export for a user and print the report."""
    if file.stat().st_size > MAX_IMPORT_BYTES:
        typer.echo(f"The file is larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB.", err=True)
        raise typer.Exit(code=1)
    try:
        job = asyncio.run(_import(username, source, file.name, file.read_bytes()))
    except (ImportFailedError, ImportFileError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None
    except ImportInProgressError:
        typer.echo(f"An import is already running for {username}.", err=True)
        raise typer.Exit(code=1) from None
    if job.status is not ImportStatus.DONE or job.report is None:
        typer.echo("The import failed; the server logs say why.", err=True)
        raise typer.Exit(code=1)
    report = job.report
    typer.echo(
        f"Imported {report['imported']}, already present {report['already_present']}, "
        f"not matched {report['unmatched_count']}."
    )
    for entry in report["unmatched"]:
        typer.echo(f"  {entry['reason']}: {entry['title']}")
