import pytest

from mintrack.core.accounts.devices import device_label

ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36"
)
IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 "
    "Mobile/15E148 Safari/604.1"
)
WINDOWS_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 "
    "Edg/131.0"
)
MAC_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 "
    "Safari/605.1.15"
)


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (ANDROID_CHROME, "Chrome on Android"),
        (IPHONE_SAFARI, "Safari on iPhone"),
        (WINDOWS_EDGE, "Edge on Windows"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0", "Firefox on Linux"),
        (MAC_SAFARI, "Safari on macOS"),
        ("Mozilla/5.0 (Linux; Android 14)", "Android"),
        ("python-httpx/0.28", None),
        (None, None),
    ],
)
def test_device_label_names_the_browser_and_the_system(user_agent: str | None, label: str | None) -> None:
    assert device_label(user_agent) == label
