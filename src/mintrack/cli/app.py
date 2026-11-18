import typer

from mintrack.cli.commands import db, healthcheck, server


def get_cli_app() -> typer.Typer:
    app = typer.Typer(name="mintrack", no_args_is_help=True, pretty_exceptions_show_locals=False)
    app.add_typer(server.command, name="server")
    app.add_typer(db.command, name="db")
    app.add_typer(healthcheck.command, name="healthcheck")
    return app
