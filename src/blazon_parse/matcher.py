import re

from blazon_parse.catalog_parser import ParsedCatalog

NUMBER_WORDS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]


def find_all(string: str, substring: str) -> list[tuple[int, int]]:
    """All (start, end) spans of substring in string, including overlapping ones."""
    return [
        (m.start(), m.start() + len(substring))
        for m in re.finditer(f"(?={re.escape(substring)})", string)
    ]


def find_matches(blazon: str, terms: list[str]) -> dict[tuple[int, int], list[str]]:
    findings: dict[tuple[int, int], list[str]] = {}

    for term in terms:
        for span in find_all(blazon, term):
            findings.setdefault(span, []).append(term)
    return findings


def find_catalog_matches(
    blazon: str, catalog: ParsedCatalog
) -> dict[tuple[int, int], list[str]]:
    blazon = blazon.lower()
    findings: dict[tuple[int, int], list[str]] = {}

    numbers = {n + 1: [f"{n + 1}", number] for n, number in enumerate(NUMBER_WORDS)}
    numbers[1].extend(["a ", "an "])

    for k, vs in numbers.items():
        for span, v in find_matches(blazon, vs).items():
            findings.setdefault(span, []).extend(f"count: {k} ({val})" for val in v)

    for term, idxs in catalog.feature_index.items():
        term = term.removeprefix("~")
        features = {
            f"feature {catalog.features[idx].feature_set} ({term})" for idx in idxs
        }
        for span in find_all(blazon, term.lower()):
            findings.setdefault(span, []).extend(features)

    for term, cats in catalog.category_lookup.items():
        categories = [f"category ({term}): {cat}" for cat in cats]
        for span in find_all(blazon, term.lower()):
            findings.setdefault(span, []).extend(categories)

    return _drop_contained(findings)


def _drop_contained(
    findings: dict[tuple[int, int], list[str]],
) -> dict[tuple[int, int], list[str]]:
    def contained_in_another(span: tuple[int, int]) -> bool:
        start, end = span
        return any(
            other_start <= start and end <= other_end
            for other_start, other_end in findings
            if (other_start, other_end) != span
        )

    return {
        span: matches
        for span, matches in findings.items()
        if not contained_in_another(span)
    }
