import email.utils
import os
from pathlib import Path

import requests

CATALOG_URL = "https://oanda.sca.org/my.cat"

# oanda.sca.org's Cloudflare front-end 403s the default python-requests
USER_AGENT = "Mozilla/5.0 (compatible; blazon-parse)"


def get_updated_catalog(dest: Path, url: str = CATALOG_URL) -> tuple[Path, bool]:
    """Download my.cat to dest if dest is missing or older than the version at url. Returns path and 'updated' boolean value."""
    headers = {"User-Agent": USER_AGENT}
    if dest.exists():
        headers["If-Modified-Since"] = email.utils.formatdate(
            dest.stat().st_mtime, usegmt=True
        )

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code == 304:
        return dest, False

    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)

    last_modified = response.headers.get("Last-Modified")
    if last_modified:
        mtime = email.utils.mktime_tz(email.utils.parsedate_tz(last_modified))
        os.utime(dest, (mtime, mtime))

    return dest, True
