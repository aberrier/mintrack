import pytest

from mintrack.cli.commands.server import proxy_setting_missing, uvicorn_options
from mintrack.config import get_config


def test_uvicorn_leaves_proxy_headers_to_the_app_and_hides_its_name() -> None:
    options = uvicorn_options(get_config(), reload=False)

    assert options["proxy_headers"] is False
    assert options["server_header"] is False
    assert (options["app"], options["factory"]) == ("mintrack.server.api.asgi:build_app", True)
    assert (options["host"], options["port"]) == ("127.0.0.1", 8000)


@pytest.mark.parametrize(
    ("public_url", "forwarded_allow_ips", "missing"),
    [
        ("https://mintrack.example.com", "", True),
        ("https://mintrack.example.com", "172.30.0.1", False),
        ("http://192.168.1.10:8000", "", False),
    ],
)
def test_an_https_address_without_a_trusted_proxy_is_warned_about(
    env: pytest.MonkeyPatch, public_url: str, forwarded_allow_ips: str, *, missing: bool
) -> None:
    env.setenv("MINTRACK__PROJECT__PUBLIC_URL", public_url)
    env.setenv("MINTRACK__SERVER__FORWARDED_ALLOW_IPS", forwarded_allow_ips)

    assert proxy_setting_missing(get_config()) is missing
