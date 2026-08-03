import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_CROSS_REFERENCE_RE = re.compile(
    r"^(?P<term>.+?) - see(?P<also> also)? (?P<targets>.+)$"
)


@dataclass
class FeatureRelation:
    """A chain of relationship tiers within a feature set.

    tiers is ordered most-specific first; each tier is a set of synonyms, and
    each tier rolls up to the next, e.g. "seme<5 or more<2 or more=6=7=8=9=10 or more"
    becomes [["seme"], ["5 or more"], ["2 or more", "6", "7", "8", "9", "10 or more"]].
    """

    feature_set: str
    tiers: list[list[str]]

    @classmethod
    def from_line(cls, line: str) -> FeatureRelation | None:
        if not line.startswith("|"):
            return None
        feature_set, _, rest = line.split("|")[-1].partition(":")
        tiers = [tier.split("=") for tier in rest.split("<")]
        return cls(feature_set=feature_set, tiers=tiers)


@dataclass
class CrossReference:
    term: str
    see_also: bool
    targets: list[str]

    @classmethod
    def from_line(cls, line: str) -> CrossReference | None:
        match = _CROSS_REFERENCE_RE.match(line)
        if not match:
            return None
        return cls(
            term=match["term"],
            see_also=match["also"] is not None,
            targets=match["targets"].split(" and "),
        )


@dataclass
class ParsedCatalog:
    features: list[FeatureRelation]
    feature_index: dict[str, list[int]]
    categories: dict[str, str]
    cross_references: list[CrossReference]

    def relations_for(self, term: str) -> list[FeatureRelation]:
        """All feature relations mentioning term, whether as a tier head or a synonym."""
        return [self.features[i] for i in self.feature_index.get(term, [])]


def parse_catalog(text: str) -> ParsedCatalog:
    features: list[FeatureRelation] = []
    categories: dict[str, str] = {}
    cross_references: list[CrossReference] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if feature := FeatureRelation.from_line(line):
            features.append(feature)
        elif cross_reference := CrossReference.from_line(line):
            cross_references.append(cross_reference)
        elif "|" in line:
            term, code = line.split("|", 1)
            categories[term] = code
        else:
            raise ValueError(f"my.cat:{lineno}: unrecognized line format: {raw_line!r}")

    feature_index: dict[str, list[int]] = {}
    for i, feature in enumerate(features):
        for tier in feature.tiers:
            for term in tier:
                feature_index.setdefault(term, []).append(i)

    return ParsedCatalog(
        features=features,
        feature_index=feature_index,
        categories=categories,
        cross_references=cross_references,
    )


def parse_catalog_file(src: Path) -> ParsedCatalog:
    return parse_catalog(src.read_text(encoding="utf-8"))


def save_parsed_catalog(parsed: ParsedCatalog, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(asdict(parsed), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_parsed_catalog(src: Path) -> ParsedCatalog:
    data = json.loads(src.read_text(encoding="utf-8"))
    return ParsedCatalog(
        features=[FeatureRelation(**f) for f in data["features"]],
        feature_index=data["feature_index"],
        categories=data["categories"],
        cross_references=[CrossReference(**c) for c in data["cross_references"]],
    )
