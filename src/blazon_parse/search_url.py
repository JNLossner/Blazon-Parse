import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import requests

from blazon_parse.catalog import USER_AGENT

OANDA_SEARCH_URL = "https://oanda.sca.org//oanda_complex.cgi"
MAX_TERMS = 10
DEFAULT_MATCH_TYPE = "armory description"
MATCH_TYPES = (DEFAULT_MATCH_TYPE, "blazon pattern", "date and kingdom")


def build_search_url(
    terms: list[str],
    *,
    weights: list[int] | None = None,
    match_types: list[str] | None = None,
    raw: bool = False,
    limit: int = 500,
) -> str:
    """An O&A complex search URL for the given search terms.

    Each term fills one of the search form's numbered rows (up to 10); the
    O&A complex search itself only supports that many. `weights` fills the
    matching "w" (importance) row per term, defaulting to 1. `raw` switches
    on the "|"-delimited raw result listing (`raw=enabled`) that
    `parse_search_results` expects, instead of the human-browsing HTML.
    `limit` caps how many results the server returns.
    """
    if len(terms) > MAX_TERMS:
        raise ValueError(
            f"O&A complex search supports at most {MAX_TERMS} terms, got {len(terms)}"
        )
    if weights is not None and len(weights) != len(terms):
        raise ValueError("weights must be the same length as terms")
    if match_types is not None and len(match_types) != len(terms):
        raise ValueError("match_types must be the same length as terms")

    params: dict[str, str] = {}
    for i in range(1, MAX_TERMS + 1):
        params[f"w{i}"] = str(weights[i - 1]) if weights and i <= len(weights) else "1"
        params[f"m{i}"] = (
            match_types[i - 1]
            if match_types and i <= len(match_types)
            else DEFAULT_MATCH_TYPE
        )
        params[f"p{i}"] = terms[i - 1] if i <= len(terms) else ""

    params.update(
        {
            "l": str(limit),
            "s": "score and blazon",
            "d": "modern",
            "g": "disabled",
            "a": "enabled",
            "raw": "enabled" if raw else "disabled",
            "rs": "all items",
        }
    )

    return f"{OANDA_SEARCH_URL}?{urlencode(params)}"


# O&A submission IDs encode the LoAR year/month and a kingdom code
# as a single trailing letter, e.g. "202005X" -> May 2020, Ansteorra.
# kingdom_codes.json is pulled from oanda_date.cgi's per-kingdom checkbox
# field names on its "search by date" form (e.g. name="kX" -> Ansteorra)
_SUBMISSION_ID_RE = re.compile(
    r"^(?P<year>\d{4})(?P<month>0[1-9]|1[0-2])(?P<kingdom>[A-Za-z])?$"
)
_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
KINGDOM_CODES: dict[str, str] = json.loads(
    (Path(__file__).parent / "kingdom_codes.json").read_text(encoding="utf-8")
)


@dataclass
class SearchResult:
    name: str
    submission_id: str
    status: str
    blazon: str
    notes: str
    armory_lines: list[str]
    score: int

    @property
    def registration_date(self) -> str | None:
        """ "Month YYYY" the item was registered, derived from `submission_id`."""
        match = _SUBMISSION_ID_RE.match(self.submission_id)
        return (
            f"{_MONTH_NAMES[int(match['month']) - 1]} {match['year']}"
            if match
            else None
        )

    @property
    def kingdom(self) -> str | None:
        """Kingdom name derived from `submission_id`'s trailing code letter, if present."""
        match = _SUBMISSION_ID_RE.match(self.submission_id)
        return (
            KINGDOM_CODES.get(match["kingdom"]) if match and match["kingdom"] else None
        )


# Raw results are grouped under headers like "Here is one matching item with
# a score of 2:" / "Here are 499 matching items with a score of 1:", each
# followed by "|"-delimited rows: name|submission_id|status|blazon|notes|
# armory_line1|armory_line2|...<br>
_SCORE_HEADER_RE = re.compile(r"with a score of (?P<score>\d+)\s*:</h4>")
_RESULT_LINE_RE = re.compile(
    r"^(?P<name>[^|\n]+)\|(?P<submission_id>[^|\n]+)\|(?P<status>[^|\n]+)\|"
    r"(?P<blazon>[^|\n]+)\|(?P<notes>[^|\n]+)\|(?P<armory>.+?)<br>$",
    re.MULTILINE,
)


def parse_search_results(html: str) -> list[SearchResult]:
    """Parse a `raw=enabled` O&A complex search response into `SearchResult`s.

    Results come back pre-sorted best-score-first, so the returned list is
    already in rank order.
    """
    results: list[SearchResult] = []
    headers = list(_SCORE_HEADER_RE.finditer(html))
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(html)
        score = int(header["score"])
        for match in _RESULT_LINE_RE.finditer(html, start, end):
            results.append(
                SearchResult(
                    name=match["name"],
                    submission_id=match["submission_id"],
                    status=match["status"],
                    blazon=match["blazon"],
                    notes=match["notes"],
                    armory_lines=match["armory"].split("|"),
                    score=score,
                )
            )
    return results


def search_oanda(
    terms: list[str],
    *,
    weights: list[int] | None = None,
    match_types: list[str] | None = None,
    limit: int = 500,
    timeout: int = 30,
) -> list[SearchResult]:
    """Run an O&A complex search for `terms` and return ranked results."""
    url = build_search_url(
        terms, weights=weights, match_types=match_types, raw=True, limit=limit
    )
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return parse_search_results(response.text)
