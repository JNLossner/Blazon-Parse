import re

from blazon_parse.feature_catalog import FeatureCatalog
from blazon_parse.heraldic import FeatureType, HeraldicFeature


def find_all(string: str, substring: str) -> list[tuple[int, int]]:
    """All (start, end) spans of substring in string, including overlapping ones."""
    return [
        (m.start(), m.start() + len(substring))
        for m in re.finditer(f"(?={re.escape(substring)})", string)
    ]


def _dedup_features(
    findings: dict[tuple[int, int], list[tuple[str, HeraldicFeature]]],
) -> dict[tuple[int, int], list[HeraldicFeature]]:
    deduped: dict[tuple[int, int], list[HeraldicFeature]] = {}
    for span, features in findings.items():
        seen_types: set[tuple[FeatureType, str]] = set()
        span_features: list[HeraldicFeature] = []
        for _, feat in features:
            key = (feat.feature_type, feat.subtype)
            if key not in seen_types:
                span_features.append(feat)
                seen_types.add(key)
        deduped[span] = span_features
    return deduped


def find_catalog_matches(
    blazon: str, catalog: FeatureCatalog
) -> dict[tuple[int, int], list[HeraldicFeature]]:
    blazon = blazon.lower()
    findings: dict[tuple[int, int], list[HeraldicFeature]] = {}

    for term in catalog.terms():
        for span in find_all(blazon, term.removeprefix("~").lower()):
            findings.setdefault(span, []).extend(catalog[term])

    return _drop_contained(findings)


def _drop_contained(
    findings: dict[tuple[int, int], list],
) -> dict[tuple[int, int], list]:
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
