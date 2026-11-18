import ipaddress
import pathlib
import typing

import pydantic
from pydantic_settings import NoDecode

type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class ServerConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    host: str = "127.0.0.1"
    port: int = pydantic.Field(default=8000, ge=1, le=65535)
    # Peers allowed to set X-Forwarded-For / X-Forwarded-Proto: comma-separated addresses or CIDR ranges.
    forwarded_allow_ips: typing.Annotated[list[IPNetwork], NoDecode] = pydantic.Field(default_factory=list)
    # The built Angular app (frontend/dist/frontend/browser). Unset: the server answers the API only, as in
    # development where `ng serve` serves the app.
    frontend_dist: pathlib.Path | None = None
    # Run the background worker inside the server process; false when `mintrack worker` runs as its own service.
    run_worker: bool = True

    @pydantic.field_validator("forwarded_allow_ips", mode="before")
    @classmethod
    def _parse_networks(cls, value: object) -> object:
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, list):
            return value
        try:
            return [ipaddress.ip_network(item, strict=False) for item in value]
        except ValueError:
            msg = "must be IP addresses or CIDR ranges separated by commas"
            raise ValueError(msg) from None

    @pydantic.field_validator("frontend_dist")
    @classmethod
    def _built_app(cls, value: pathlib.Path | None) -> pathlib.Path | None:
        if value is None:
            return None
        if not (value / "index.html").is_file():
            msg = "must be the folder of the built app, holding index.html"
            raise ValueError(msg)
        if (value / "pyproject.toml").exists():
            # A path mistake that would publish the source tree (and maybe a .env) over HTTP.
            msg = "points at the repository, not at the built app"
            raise ValueError(msg)
        return value.resolve()

    @property
    def trusted_proxies(self) -> list[str]:
        return [str(network) for network in self.forwarded_allow_ips]
