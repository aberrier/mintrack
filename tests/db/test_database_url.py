import pydantic
import pytest
from sqlalchemy.engine import make_url

from mintrack.db.config import DatabaseConfig, SSLMode

PASSWORD = "p@ss/w:rd%#?&=value"


def test_password_with_url_special_characters_survives_the_url() -> None:
    config = DatabaseConfig(host="db", user="mintrack", password=pydantic.SecretStr(PASSWORD), name="mintrack")

    parsed = make_url(config.url().render_as_string(hide_password=False))

    assert parsed.password == PASSWORD
    assert (parsed.drivername, parsed.host, parsed.port, parsed.database) == (
        "postgresql+psycopg",
        "db",
        5432,
        "mintrack",
    )


@pytest.mark.parametrize(("sslmode", "query"), [(None, {}), (SSLMode.VERIFY_FULL, {"sslmode": "verify-full"})])
def test_sslmode_is_passed_only_when_set(sslmode: SSLMode | None, query: dict[str, str]) -> None:
    config = DatabaseConfig(host="db", user="u", password=pydantic.SecretStr("p"), name="n", sslmode=sslmode)

    assert dict(config.url().query) == query


def test_url_can_target_another_database() -> None:
    config = DatabaseConfig(host="db", user="u", password=pydantic.SecretStr("p"), name="mintrack")

    assert config.url(database="test_mintrack").database == "test_mintrack"
