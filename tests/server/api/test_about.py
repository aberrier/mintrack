import httpx

from mintrack.config import get_config


async def test_about_gives_the_version_and_the_mcp_address_on_the_public_url(signed_in: httpx.AsyncClient) -> None:
    about = (await signed_in.get("/api/about")).json()

    assert about == {"version": get_config().project.version, "mcp_url": "https://mintrack.test/mcp"}


async def test_the_time_zones_list_current_names_with_their_legacy_ones(signed_in: httpx.AsyncClient) -> None:
    zones = {zone["name"]: zone["aliases"] for zone in (await signed_in.get("/api/auth/timezones")).json()}

    assert "Asia/Calcutta" in zones["Asia/Kolkata"]
