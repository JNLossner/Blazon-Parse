import re
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from blazon_parse.catalog import USER_AGENT

OANDA_SEARCH_URL = "https://oanda.sca.org//oanda_complex.cgi"
MAX_TERMS = 10


def build_search_url(terms: list[str], *, raw: bool = False, limit: int = 500) -> str:
    """An O&A complex search URL for the given armory description terms.

    Each term fills one of the search form's numbered "armory description"
    rows (up to 10); the O&A complex search itself only supports that many.
    `raw` switches on the "|"-delimited raw result listing (`raw=enabled`)
    that `parse_search_results` expects, instead of the human-browsing HTML.
    `limit` caps how many results the server returns.
    """
    if len(terms) > MAX_TERMS:
        raise ValueError(
            f"O&A complex search supports at most {MAX_TERMS} terms, got {len(terms)}"
        )

    params: dict[str, str] = {}
    for i in range(1, MAX_TERMS + 1):
        params[f"w{i}"] = "1"
        params[f"m{i}"] = "armory description"
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


@dataclass
class SearchResult:
    name: str
    submission_id: str
    status: str
    blazon: str
    notes: str
    armory_lines: list[str]
    score: int


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
    terms: list[str], *, limit: int = 500, timeout: int = 30
) -> list[SearchResult]:
    """Run an O&A complex search for `terms` and return ranked results."""
    url = build_search_url(terms, raw=True, limit=limit)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return parse_search_results(response.text)
