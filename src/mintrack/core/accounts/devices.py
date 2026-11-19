import re

USER_AGENT_MAX_LENGTH = 512

# The first match wins: Edge and Opera also say Chrome, Chrome also says Safari, Android also says Linux.
_BROWSERS = [
    ("Edge", re.compile(r"\bEdg(e|A|iOS)?/")),
    ("Opera", re.compile(r"\b(OPR|Opera)/")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/")),
    ("Firefox", re.compile(r"\b(Firefox|FxiOS)/")),
    ("Chrome", re.compile(r"\b(Chrome|CriOS)/")),
    ("Safari", re.compile(r"\bSafari/")),
]
_SYSTEMS = [
    ("iPhone", re.compile(r"\biPhone\b")),
    ("iPad", re.compile(r"\biPad\b")),
    ("Android", re.compile(r"\bAndroid\b")),
    ("ChromeOS", re.compile(r"\bCrOS\b")),
    ("Windows", re.compile(r"\bWindows\b")),
    ("macOS", re.compile(r"\bMac OS X\b")),
    ("Linux", re.compile(r"\bLinux\b")),
]


def _first(candidates: list[tuple[str, re.Pattern[str]]], user_agent: str) -> str | None:
    return next((name for name, pattern in candidates if pattern.search(user_agent)), None)


def device_label(user_agent: str | None) -> str | None:
    """A readable name for the device behind a User-Agent, such as "Chrome on Android"; None when nothing is known."""
    if not user_agent:
        return None
    browser, system = _first(_BROWSERS, user_agent), _first(_SYSTEMS, user_agent)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system
