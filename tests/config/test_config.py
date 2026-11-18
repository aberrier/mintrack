import pathlib

import pydantic
import pytest

import mintrack.config
from mintrack.config import Config, ConfigError, Environment, load_config
from mintrack.config.security import SECRET_KEY_PLACEHOLDER
from tests.conftest import DATABASE_PASSWORD

SECRET_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def problems(env: pytest.MonkeyPatch) -> list[str]:
    with pytest.raises(ConfigError) as error:
        load_config(env_file=None)
    return error.value.problems


def test_defaults_need_only_the_database(env: pytest.MonkeyPatch) -> None:
    config = load_config(env_file=None)

    assert config.project.environment is Environment.DEV
    assert config.project.public_origin == "http://localhost:8000"
    assert config.server.trusted_proxies == []
    assert config.logging.sentry_dsn is None


def test_each_missing_database_field_is_named_by_its_variable(env: pytest.MonkeyPatch) -> None:
    for field in ("HOST", "USER", "PASSWORD", "NAME"):
        env.delenv(f"MINTRACK__DATABASE__{field}")

    assert problems(env) == [
        "MINTRACK__DATABASE__HOST: Field required",
        "MINTRACK__DATABASE__USER: Field required",
        "MINTRACK__DATABASE__PASSWORD: Field required",
        "MINTRACK__DATABASE__NAME: Field required",
    ]


def test_empty_database_values_are_rejected(env: pytest.MonkeyPatch) -> None:
    # An unset compose variable arrives as an empty string.
    env.setenv("MINTRACK__DATABASE__HOST", "")
    env.setenv("MINTRACK__DATABASE__PASSWORD", "")

    assert problems(env) == [
        "MINTRACK__DATABASE__HOST: String should have at least 1 character",
        "MINTRACK__DATABASE__PASSWORD: must not be empty",
    ]


def test_secrets_are_hidden_in_the_config_representation(env: pytest.MonkeyPatch) -> None:
    env.setenv("MINTRACK__SECURITY__SECRET_KEY", SECRET_KEY)

    rendered = repr(load_config(env_file=None))

    assert SECRET_KEY not in rendered
    assert DATABASE_PASSWORD not in rendered


def test_prod_requires_a_secret_key(env: pytest.MonkeyPatch) -> None:
    env.setenv("MINTRACK__PROJECT__ENVIRONMENT", "prod")

    assert problems(env) == [
        "MINTRACK__SECURITY__SECRET_KEY: is required in prod; generate one with `openssl rand -hex 32`"
    ]

    env.setenv("MINTRACK__SECURITY__SECRET_KEY", SECRET_KEY)
    assert load_config(env_file=None).security.secret_key is not None


@pytest.mark.parametrize(
    ("secret_key", "problem"),
    [
        (SECRET_KEY_PLACEHOLDER, "is still the .env.example placeholder"),
        ("too-short-secret", "must be at least 32 characters"),
    ],
)
def test_prod_rejects_weak_secret_keys_without_echoing_them(
    env: pytest.MonkeyPatch, secret_key: str, problem: str
) -> None:
    env.setenv("MINTRACK__SECURITY__SECRET_KEY", secret_key)
    assert load_config(env_file=None).security.secret_key is not None

    env.setenv("MINTRACK__PROJECT__ENVIRONMENT", "prod")
    reported = problems(env)

    assert reported == [f"MINTRACK__SECURITY__SECRET_KEY: {problem}; generate one with `openssl rand -hex 32`"]
    assert secret_key not in reported[0]


@pytest.mark.parametrize("url", ["http://192.168.1.20:8000", "https://mintrack.example.com/"])
def test_public_url_accepts_http_and_https_origins(env: pytest.MonkeyPatch, url: str) -> None:
    env.setenv("MINTRACK__PROJECT__PUBLIC_URL", url)

    assert load_config(env_file=None).project.public_origin == url.removesuffix("/")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/mintrack",
        "https://mintrack.example.com/?next=1",
        "https://user:password@mintrack.example.com",
        "ftp://mintrack.example.com",
    ],
)
def test_public_url_must_be_the_root_of_an_origin(env: pytest.MonkeyPatch, url: str) -> None:
    env.setenv("MINTRACK__PROJECT__PUBLIC_URL", url)

    assert [problem.split(":")[0] for problem in problems(env)] == ["MINTRACK__PROJECT__PUBLIC_URL"]


def test_forwarded_allow_ips_takes_addresses_and_ranges(env: pytest.MonkeyPatch) -> None:
    env.setenv("MINTRACK__SERVER__FORWARDED_ALLOW_IPS", "172.30.0.1, 10.0.0.0/8,fd00::/8")

    assert load_config(env_file=None).server.trusted_proxies == ["172.30.0.1/32", "10.0.0.0/8", "fd00::/8"]

    env.setenv("MINTRACK__SERVER__FORWARDED_ALLOW_IPS", "172.30.0.1,proxy")
    assert [problem.split(":")[0] for problem in problems(env)] == ["MINTRACK__SERVER__FORWARDED_ALLOW_IPS"]


def test_file_variables_read_secrets_from_files(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    secret_file = tmp_path / "secret_key"
    secret_file.write_text(SECRET_KEY + "\n", encoding="utf-8")
    password_file = tmp_path / "db_password"
    password_file.write_text("from-a-file\n", encoding="utf-8")
    env.delenv("MINTRACK__DATABASE__PASSWORD")
    env.setenv("MINTRACK__SECURITY__SECRET_KEY_FILE", str(secret_file))
    env.setenv("MINTRACK__DATABASE__PASSWORD_FILE", str(password_file))

    config = load_config(env_file=None)

    assert config.security.secret_key is not None
    assert config.security.secret_key.get_secret_value() == SECRET_KEY
    assert config.database.password.get_secret_value() == "from-a-file"


def test_a_variable_set_directly_wins_over_its_file(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    password_file = tmp_path / "db_password"
    password_file.write_text("from-a-file", encoding="utf-8")
    env.setenv("MINTRACK__DATABASE__PASSWORD_FILE", str(password_file))

    assert load_config(env_file=None).database.password.get_secret_value() == DATABASE_PASSWORD

    # An unset compose variable arrives empty: the file then wins.
    env.setenv("MINTRACK__DATABASE__PASSWORD", "")
    assert load_config(env_file=None).database.password.get_secret_value() == "from-a-file"


def test_a_relative_file_variable_names_a_docker_secret(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    env.setattr(mintrack.config, "DOCKER_SECRETS_DIR", tmp_path)
    (tmp_path / "mintrack_db_password").write_text("  from-a-secret \n", encoding="utf-8")
    env.delenv("MINTRACK__DATABASE__PASSWORD")
    env.setenv("MINTRACK__DATABASE__PASSWORD_FILE", "mintrack_db_password")

    assert load_config(env_file=None).database.password.get_secret_value() == "from-a-secret"


def test_an_unreadable_file_variable_is_named(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    env.setenv("MINTRACK__SECURITY__SECRET_KEY_FILE", str(tmp_path / "missing"))

    assert problems(env) == [
        "MINTRACK__SECURITY__SECRET_KEY_FILE: cannot read the file it names (No such file or directory)"
    ]


def test_dotenv_file_is_read(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    env.delenv("MINTRACK__DATABASE__PASSWORD")
    (tmp_path / ".env").write_text("MINTRACK__DATABASE__PASSWORD=from-dotenv\n", encoding="utf-8")

    assert load_config().database.password.get_secret_value() == "from-dotenv"


def test_a_file_variable_naming_binary_data_is_reported(env: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    secret_file = tmp_path / "secret_key"
    secret_file.write_bytes(b"\xff\xfe\x00raw-bytes")
    env.setenv("MINTRACK__SECURITY__SECRET_KEY_FILE", str(secret_file))

    assert problems(env) == ["MINTRACK__SECURITY__SECRET_KEY_FILE: the file it names is not UTF-8 text"]


def test_rejected_values_are_never_echoed(env: pytest.MonkeyPatch) -> None:
    env.setenv("MINTRACK__DATABASE__PORT", "not-a-port")
    env.setenv("MINTRACK__SERVER__FORWARDED_ALLOW_IPS", "internal-proxy-name")

    assert [problem.split(":")[0] for problem in problems(env)] == [
        "MINTRACK__SERVER__FORWARDED_ALLOW_IPS",
        "MINTRACK__DATABASE__PORT",
    ]
    with pytest.raises(pydantic.ValidationError) as error:
        Config(_env_file=None)
    assert "not-a-port" not in str(error.value)
    assert "internal-proxy-name" not in str(error.value)
