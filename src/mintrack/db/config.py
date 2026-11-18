import enum
import typing

import pydantic
from sqlalchemy.engine import URL

# psycopg 3 drives both the async engine and Alembic's synchronous one.
DRIVER = "postgresql+psycopg"
# Seconds before a connection attempt fails, instead of the operating system's TCP timeout.
CONNECT_ARGS = {"connect_timeout": 5}

NonEmptyStr = typing.Annotated[str, pydantic.Field(min_length=1)]


class SSLMode(enum.StrEnum):
    DISABLE = "disable"
    ALLOW = "allow"
    PREFER = "prefer"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


class DatabaseConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    host: NonEmptyStr
    port: int = pydantic.Field(default=5432, ge=1, le=65535)
    user: NonEmptyStr
    password: pydantic.SecretStr
    name: NonEmptyStr
    sslmode: SSLMode | None = None

    @pydantic.field_validator("password")
    @classmethod
    def _password_not_empty(cls, value: pydantic.SecretStr) -> pydantic.SecretStr:
        if not value.get_secret_value():
            msg = "must not be empty"
            raise ValueError(msg)
        return value

    def url(self, *, database: str | None = None) -> URL:
        # URL.create escapes the password, so it may contain any character.
        return URL.create(
            drivername=DRIVER,
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=database or self.name,
            query={"sslmode": self.sslmode.value} if self.sslmode else {},
        )
