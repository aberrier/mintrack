import asyncio
import datetime as dt
import typing

import typer

from mintrack.config import get_config
from mintrack.core.accounts.managers import (
    AccountManager,
    InvalidUsernameError,
    UserDisabledError,
    UsernameTakenError,
)
from mintrack.core.accounts.tokens import password_link
from mintrack.db.database import DatabaseManager

command = typer.Typer(no_args_is_help=True, help="User accounts.")

Username = typing.Annotated[str, typer.Argument(help="The username, case-insensitive.")]


async def _run[T](action: typing.Callable[[AccountManager], typing.Awaitable[T]]) -> T:
    """Run an action on a manager in its own transaction, committed when it returns."""
    database = DatabaseManager(get_config().database.url())
    try:
        async with database.session() as session:
            result = await action(AccountManager(session))
            await session.commit()
            return result
    finally:
        await database.close()


async def _create_admin(manager: AccountManager, username: str) -> str:
    _, token = await manager.create_user(username, is_admin=True, now=dt.datetime.now(dt.UTC))
    return token


async def _reset_link(manager: AccountManager, username: str) -> str | None:
    user = await manager.get_user(username)
    return None if user is None else manager.issue_link(user, now=dt.datetime.now(dt.UTC))


def _fail(message: str) -> typing.NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@command.command("create-admin")
def create_admin(username: Username) -> None:
    """Create an admin without a password and print the link that sets it."""
    try:
        token = asyncio.run(_run(lambda manager: _create_admin(manager, username)))
    except InvalidUsernameError:
        _fail("A username is 1 to 150 letters, digits, dots, dashes or underscores.")
    except UsernameTakenError:
        _fail(f"The username {username} is taken.")
    typer.echo(password_link(get_config().project.public_origin, token))


@command.command("reset-link")
def reset_link(username: Username) -> None:
    """Print a new link that sets the user's password; their previous link stops working."""
    try:
        token = asyncio.run(_run(lambda manager: _reset_link(manager, username)))
    except UserDisabledError:
        _fail(f"{username} is disabled; enable them from the users page first.")
    if token is None:
        _fail(f"No user named {username}.")
    typer.echo(password_link(get_config().project.public_origin, token))
