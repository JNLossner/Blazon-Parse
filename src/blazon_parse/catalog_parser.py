import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from blazon_parse.heraldic import HeraldicFeature, to_feature_type

_CROSS_REFERENCE_RE = re.compile(
    r"^(?P<term>.+?) - see(?P<also> also)? (?P<targets>.+)$"
)

# Da'ud notation: my.cat's ASCII-safe encoding for accented characters.
# Full reference: https://heraldry.sca.org/daud_notation.pdf
_DAUD_CHARACTERS: dict[str, str] = json.loads(
    (Path(__file__).parent / "daud_notation.json").read_text(encoding="utf-8")
)
_DAUD_RE = re.compile(r"\{([^{}]*)\}")


def decode_daud(text: str) -> str:
    """Replace {code} sequences with their Unicode character; leave unknown codes as-is."""

    def replace(match: re.Match[str]) -> str:
        return _DAUD_CHARACTERS.get(match[1], match[0])

    return _DAUD_RE.sub(replace, text)


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
class Category:
    heraldic: HeraldicFeature
    category: str
    terms: list[str]

    @classmethod
    def from_line(cls, line: str) -> Category | None:
        if line.startswith("|") or "|" not in line:
            return None
        category, code = line.split("|", 1)
        term = category

        cat_parts = [s.strip() for s in category.split(",") if "as charge" not in s]
        cat_type = cat_parts[0]
        subtype = ""

        words = cat_type.split(" ")
        term = " ".join([word for word in words if word != "field"])

        if len(cat_parts) > 1:
            term = " ".join(cat_parts[1:])

        if len(cat_parts) > 2 and cat_type not in [
            "monster",
            "charge treatment",
            "field treatment",
        ]:
            subtype = cat_parts[1]
            term = " ".join(cat_parts[2:])

        return cls(
            heraldic=HeraldicFeature(
                feature_type=to_feature_type(category), subtype=subtype, code=code
            ),
            category=category,
            terms=[]
            if not term or term.startswith("not") or term == "other"
            else [term],
        )


@dataclass
class ParsedCatalog:
    features: list[FeatureRelation]
    feature_index: dict[str, list[int]]
    categories: dict[str, Category]
    category_lookup: dict[str, list[str]]
    cross_references: list[CrossReference]

    def relations_for(self, term: str) -> list[FeatureRelation]:
        """All feature relations mentioning term, whether as a tier head or a synonym."""
        return [self.features[i] for i in self.feature_index.get(term, [])]


def parse_catalog(text: str) -> ParsedCatalog:
    features: list[FeatureRelation] = []
    categories: dict[str, Category] = {}
    cross_references: list[CrossReference] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = decode_daud(raw_line.strip())
        if not line:
            continue

        if feature := FeatureRelation.from_line(line):
            features.append(feature)
        elif cross_reference := CrossReference.from_line(line):
            cross_references.append(cross_reference)
        elif category := Category.from_line(line):
            categories[category.category] = category
        else:
            raise ValueError(f"my.cat:{lineno}: unrecognized line format: {raw_line!r}")

    feature_index: dict[str, list[int]] = {}
    for i, feature in enumerate(features):
        for tier in feature.tiers:
            for term in tier:
                feature_index.setdefault(term, []).append(i)

    for reference in cross_references:
        for cat in reference.targets:
            if cat in categories:
                categories[cat].terms.append(reference.term)

    category_lookup: dict[str, list[str]] = {}
    for key, category in categories.items():
        for term in category.terms:
            category_lookup.setdefault(term, []).append(key)

    return ParsedCatalog(
        features=features,
        feature_index=feature_index,
        categories=categories,
        category_lookup=category_lookup,
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
        categories={
            k: Category(
                heraldic=HeraldicFeature(**v["heraldic"]), category=k, terms=v["terms"]
            )
            for k, v in data["categories"].items()
        },
        category_lookup=data["category_lookup"],
        cross_references=[CrossReference(**c) for c in data["cross_references"]],
    )
