import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a `.env` file, without overriding vars already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(PROJECT_ROOT / ".env")

# Full O&A complex-search endpoint. Point this at a local mirror (e.g. the
# ltanzos/oanda docker image) during testing to avoid hitting the real site.
OANDA_SEARCH_URL = os.environ.get(
    "OANDA_SEARCH_URL", "https://oanda.sca.org//oanda_complex.cgi"
)

WEB_HOST = os.environ.get("BLAZON_PARSE_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("BLAZON_PARSE_PORT", "8000"))
