import alembic.command
import alembic.config
from sqlalchemy.engine import URL


def get_alembic_config(url: URL) -> alembic.config.Config:
    """Build the Alembic configuration in code, so migrations run from the installed package (no alembic.ini)."""
    config = alembic.config.Config()
    config.set_main_option("script_location", "mintrack.db:migrations")
    config.set_main_option("file_template", "%%(rev)s_%%(slug)s")
    config.set_main_option("timezone", "UTC")
    config.set_section_option("post_write_hooks", "hooks", "ruff_check, ruff_format")
    config.set_section_option("post_write_hooks", "ruff_check.type", "exec")
    config.set_section_option("post_write_hooks", "ruff_check.executable", "ruff")
    config.set_section_option(
        "post_write_hooks", "ruff_check.options", "check --fix-only --exit-zero REVISION_SCRIPT_FILENAME"
    )
    config.set_section_option("post_write_hooks", "ruff_format.type", "exec")
    config.set_section_option("post_write_hooks", "ruff_format.executable", "ruff")
    config.set_section_option("post_write_hooks", "ruff_format.options", "format --quiet REVISION_SCRIPT_FILENAME")
    config.attributes["url"] = url
    return config


def upgrade(url: URL, revision: str = "heads") -> None:
    alembic.command.upgrade(get_alembic_config(url), revision)


def make_revision(url: URL, message: str) -> None:
    alembic.command.revision(get_alembic_config(url), message=message, autogenerate=True)
