import ipaddress
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

    @property
    def trusted_proxies(self) -> list[str]:
        return [str(network) for network in self.forwarded_allow_ips]
