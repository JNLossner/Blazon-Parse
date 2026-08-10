import json
import re
from collections.abc import KeysView
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

import inflect

from blazon_parse.heraldic import (
    FeatureType,
    HeraldicFeature,
    category_feature_type,
    relation_feature_type,
)

_inflect = inflect.engine()
_COUNT_TERM_RE = re.compile(r"^(?P<prefix>of )?(?P<digit>\d+)$")
_PER_DIVISION_RE = re.compile(
    r"^per (?P<direction>bend|chevron|fess|pale|pall|saltire)(?P<modifier> .+)?$"
)

_CROSS_REFERENCE_RE = re.compile(
    r"^(?P<term>.+?) - see(?P<also> also)? (?P<targets>.+)$"
)

# Da'ud notation: my.cat's ASCII-safe encoding for accented characters.
# Full reference: https://heraldry.sca.org/daud_notation.pdf
_DAUD_CHARACTERS: dict[str, str] = json.loads(
    (Path(__file__).parent / "daud_notation.json").read_text(encoding="utf-8")
)
_DAUD_RE = re.compile(r"\{([^{}]*)\}")

# Domain knowledge my.cat doesn't encode
_HERALDIC_KNOWLEDGE: dict = json.loads(
    (Path(__file__).parent / "heraldic_knowledge.json").read_text(encoding="utf-8")
)


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


# Trailing qualifiers with no literal word of their own in blazon text -
# "heraldic" marks the unmarked default.
_DROPPED_QUALIFIERS = {"heraldic"}

_JOINED_TERM_CATEGORIES = {"monster", "charge treatment", "field treatment"}

# A 2-part category's second segment is normally the term ("field division,
# per bend" -> "per bend"). For a body-part like "leg, bird" this is backwards.
_CREATURE_SCOPE_WORDS = {"beast", "bird", "fish", "monster", "reptile", "human"}

# "throughout" is real vocabulary that only occurs paired with its charge,
# so the terms are indexed under both the bare charge name and the compound phrase.
_COMPOUND_TERM_OVERRIDES: dict[str, list[str]] = {
    "cross, throughout": ["cross", "cross throughout"],
    "saltire, throughout": ["saltire", "saltire throughout"],
}


def _cat_parts(category: str) -> list[str]:
    return [
        s.strip()
        for s in category.split(",")
        if "as charge" not in s and s.strip() not in _DROPPED_QUALIFIERS
    ]


def _category_term(cat_parts: list[str]) -> str:
    if len(cat_parts) <= 1:
        return " ".join(cat_parts)
    if len(cat_parts) > 2 and cat_parts[0] not in _JOINED_TERM_CATEGORIES:
        return " ".join(cat_parts[2:])
    return " ".join(cat_parts[1:])


@dataclass
class Category:
    heraldic: HeraldicFeature
    category: str
    terms: list[str]
    # For 3-part categories, the outer name (e.g. "arrangement" in
    # "arrangement, creature, addorsed") - the *fixed* dimension, as opposed
    # to cat_parts[1] which becomes `subtype` and varies. None otherwise.
    # Keeps merge_key in parse_catalog() from conflating unrelated categories
    # that only coincidentally share a term (e.g. "beast, cat" the animal vs
    # "head, beast, cat" a cat's head, both ending in the term "cat").
    kind: str | None = None
    # False for _COMPOUND_TERM_OVERRIDES entries - they share a term with an
    # unrelated feature deliberately (e.g. "cross, as charge" and
    # "cross, throughout" both reachable via bare "cross"), not because
    # they're the same concept in different scopes like "demi" is.
    mergeable: bool = True

    @classmethod
    def from_line(cls, line: str) -> Category | None:
        if line.startswith("|") or "|" not in line:
            return None
        category, code = line.split("|", 1)

        cat_parts = _cat_parts(category)
        cat_type = cat_parts[0] if cat_parts else category
        feature_type = category_feature_type(cat_type)
        subtype = ""
        kind = None
        term = _category_term(cat_parts)

        if len(cat_parts) > 2 and cat_type not in _JOINED_TERM_CATEGORIES:
            subtype = cat_parts[1]
            kind = cat_type
        elif len(cat_parts) == 2 and cat_parts[1] in _CREATURE_SCOPE_WORDS:
            term = cat_type
            subtype = cat_parts[1]
        elif len(cat_parts) == 2:
            subtype = cat_type

        codes = {subtype: code}
        details = None
        if " field" in term:
            term = term.replace(" field", "")
            details = term
            codes = {
                "field": code,
                "FIELD": f"FIELD:{term}:solid",
                "tincture": details,
                "tincture1": details,
                "tincture2": f"~ and {details}",
            }
            feature_type = FeatureType.tincture
            details = term

        if override := _COMPOUND_TERM_OVERRIDES.get(category):
            terms = override
            mergeable = False
        elif (
            not term
            or term.startswith("not")
            or term in ("other", "whole", "throughout")
        ):
            terms = []
            mergeable = True
        else:
            terms = [term]
            mergeable = True

        return cls(
            heraldic=HeraldicFeature(
                feature_type=feature_type,
                subtype=subtype,
                codes=codes,
                details=details,
            ),
            category=category,
            terms=terms,
            kind=kind,
            mergeable=mergeable,
        )


def _pluralize(term: str) -> str:
    plural = _inflect.plural_noun(term)
    return plural if plural else term


def _add_plural_keys(
    features: list[HeraldicFeature], term_index: dict[str, list[int]]
) -> None:
    """Add each charge term's plural as an additional key mapping to the same values.

    Blazons commonly use the plural (e.g. "three roses"), so charge lookups
    need to recognize both forms.
    """
    for term in list(term_index):
        idxs = term_index[term]
        if not any(features[i].feature_type == FeatureType.charge for i in idxs):
            continue
        plural = _pluralize(term)
        if plural != term:
            for idx in idxs:
                _index_term(term_index, plural, idx)


@dataclass
class FeatureCatalog:
    relations: list[FeatureRelation]
    features: list[HeraldicFeature]
    term_index: dict[str, list[int]]
    category_index: dict[str, int] = dataclass_field(default_factory=dict)
    seme_fallback_code: str = ""
    creature_subtypes: list[str] = dataclass_field(default_factory=list)
    preferred_ambiguous_codes: list[str] = dataclass_field(default_factory=list)

    def __post_init__(self) -> None:
        # Derived indexes, rebuilt from term_index/category_index.
        self._type_terms: dict[FeatureType, set[str]] = {}
        self._terms_by_feature: dict[int, set[str]] = {}
        for term, idxs in self.term_index.items():
            for idx in idxs:
                self._terms_by_feature.setdefault(idx, set()).add(term)
                feature_type = self.features[idx].feature_type
                self._type_terms.setdefault(feature_type, set()).add(term)

        self._categories_by_feature: dict[int, set[str]] = {}
        for category, idx in self.category_index.items():
            self._categories_by_feature.setdefault(idx, set()).add(category)

    def __getitem__(self, term: str) -> list[HeraldicFeature]:
        return [self.features[i] for i in self.term_index.get(term, [])]

    def terms(self) -> KeysView[str]:
        return self.term_index.keys()

    def terms_of_type(self, *types: FeatureType) -> list[str]:
        """All indexed terms whose feature is one of `types`."""
        return sorted(
            {
                t
                for feature_type in types
                for t in self._type_terms.get(feature_type, ())
            }
        )

    def terms_for(self, idx: int) -> list[str]:
        """Every term that resolves to `features[idx]` - the reverse of term_index."""
        return sorted(self._terms_by_feature.get(idx, ()))

    def categories_for(self, idx: int) -> list[str]:
        """Every my.cat category line that resolves to `features[idx]` - the reverse of category_index."""
        return sorted(self._categories_by_feature.get(idx, ()))


def _index_term(term_index: dict[str, list[int]], term: str, idx: int) -> None:
    """Map term -> idx, skipping it if already mapped."""
    indices = term_index.setdefault(term, [])
    if idx not in indices:
        indices.append(idx)


def _divided_term(per_term: str) -> str | None:
    """ "per bend sinister" -> "divided bendwise sinister"; None if not a "per X" division."""
    if not (match := _PER_DIVISION_RE.match(per_term)):
        return None
    return f"divided {match['direction']}wise{match['modifier'] or ''}"


def _add_division_tags(
    features: list[HeraldicFeature], term_index: dict[str, list[int]]
) -> None:
    """Cross-reference a "per X" division code with "divided Xwise" classification."""
    for term, idxs in list(term_index.items()):
        if (divided_term := _divided_term(term)) is None:
            continue
        if not term_index.get(divided_term):
            continue
        for idx in idxs:
            feat = features[idx]
            if feat.feature_type == FeatureType.field_division:
                feat.codes.setdefault("divided", divided_term)


def _add_peripheral_subtype(
    features: list[HeraldicFeature], category_index: dict[str, int]
) -> None:
    """Mark peripheral ordinaries (chief, bordure, ...) via `subtype`, per
    `_HERALDIC_KNOWLEDGE["peripheral_charges"]`.
    """
    for category in _HERALDIC_KNOWLEDGE["peripheral_charges"]:
        idx = category_index.get(category)
        if idx is None:
            continue
        feat = features[idx]
        feat.codes["peripheral"] = feat.code
        feat.subtype = "peripheral"


def _add_extra_term_aliases(
    category_index: dict[str, int], term_index: dict[str, list[int]]
) -> None:
    """Link a bare term to additional category names it should also match"""
    for term, categories in _HERALDIC_KNOWLEDGE.get("extra_term_aliases", {}).items():
        for category in categories:
            if (idx := category_index.get(category)) is not None:
                _index_term(term_index, term, idx)


_SEME_TREATMENT_PREFIX = "field treatment, seme, "


def _add_seme_features(
    features: list[HeraldicFeature],
    category_index: dict[str, int],
    term_index: dict[str, list[int]],
    cross_references: list[CrossReference],
) -> str:
    """Recognize "semy of X" field patterns (e.g. "semy-de-lys azure" ->
    `FDL:azure:seme:seme on field` + `FIELD TREATMENT-SEME (DE-LYS):azure`)

    Retypes the bare "seme"/"semy" quantity terms into a generic
    `field_treatment` marker (`subtype="seme"`, `details="other"`, coded with
    the "(9OTHER)" fallback) - the actual charge is only known once a real
    blazon supplies one (see `_complete_generic_seme` in blazon_parser.py).
    For each named variant ("field treatment, seme, de lys - see also fleur
    de lys"), retypes that catalog entry the same way and links it to its
    charge's own code via `codes["charge"]`. If my.cat also has a direct
    phrase alias for it ("semy de lys - see fleur de lys"), repoints that
    alias at the named variant instead of the bare charge, so blazon text
    resolves the whole pattern in one match, with no separate "semy" word
    to notice. Returns the "(9OTHER)" fallback code.
    """
    fallback_idx = category_index.get(f"{_SEME_TREATMENT_PREFIX}other")
    fallback_code = (
        features[fallback_idx].codes.get("", "") if fallback_idx is not None else ""
    )

    for idxs in term_index.values():
        for idx in idxs:
            feat = features[idx]
            if feat.feature_type == FeatureType.count and feat.details in (
                "seme",
                "semy",
            ):
                feat.feature_type = FeatureType.field_treatment
                feat.subtype = "seme"
                feat.details = "other"
                feat.codes["seme"] = fallback_code

    phrase_aliases = [
        ref for ref in cross_references if ref.term.startswith(("semy ", "seme "))
    ]

    for reference in cross_references:
        if (
            not reference.term.startswith(_SEME_TREATMENT_PREFIX)
            or not reference.targets
        ):
            continue
        seme_idx = category_index.get(reference.term)
        target_idx = category_index.get(reference.targets[0])
        if seme_idx is None or target_idx is None:
            continue
        seme_feat = features[seme_idx]
        charge_code = features[target_idx].code
        if not seme_feat.codes.get("") or not charge_code:
            continue

        seme_feat.subtype = "seme"
        seme_feat.details = reference.term.removeprefix(_SEME_TREATMENT_PREFIX)
        seme_feat.codes["seme"] = seme_feat.codes[""]
        seme_feat.codes["charge"] = charge_code

        for alias in phrase_aliases:
            if alias.targets == reference.targets:
                term_index[alias.term] = [seme_idx]

    return fallback_code


def _add_group_participle_terms(term_index: dict[str, list[int]]) -> None:
    """Index each charged term's present-participle form too."""
    for base, participle in _HERALDIC_KNOWLEDGE["group_participles"].items():
        for idx in term_index.get(base, []):
            _index_term(term_index, participle, idx)


def _add_count_word_terms(term_index: dict[str, list[int]]) -> None:
    """Index each digit term's word form too ("3"/"of 3" -> "three"/"of three")."""
    for term in list(term_index):
        if not (match := _COUNT_TERM_RE.match(term)):
            continue
        prefix = match["prefix"] or ""
        word = prefix + _inflect.number_to_words(int(match["digit"]))
        keys = [word, "a", "an"] if term == "1" else [word]
        for idx in term_index[term]:
            for key in keys:
                _index_term(term_index, key, idx)


def parse_catalog(text: str) -> FeatureCatalog:
    relations: list[FeatureRelation] = []
    features: list[HeraldicFeature] = []
    category_index: dict[str, int] = {}
    term_index: dict[str, list[int]] = {}
    cross_references: list[CrossReference] = []

    # Some terms (e.g. "demi") appear as separate my.cat lines per governing
    # type, each with its own code; merge_index finds the earlier feature for
    # the same (feature_type, term, kind) so later lines merge their code
    # into its `codes` dict instead of becoming an unrelated duplicate.
    merge_index: dict[tuple, int] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = decode_daud(raw_line.strip())
        if not line:
            continue

        if relation := FeatureRelation.from_line(line):
            relations.append(relation)
        elif cross_reference := CrossReference.from_line(line):
            cross_references.append(cross_reference)
        elif category := Category.from_line(line):
            primary_term = category.terms[0] if category.terms else None
            merge_key = (
                (category.heraldic.feature_type, primary_term, category.kind)
                if primary_term and category.mergeable
                else None
            )
            if merge_key and (idx := merge_index.get(merge_key)) is not None:
                features[idx].codes.update(category.heraldic.codes)
            else:
                features.append(category.heraldic)
                idx = len(features) - 1
                if merge_key:
                    merge_index[merge_key] = idx
            for term in category.terms:
                _index_term(term_index, term, idx)
            category_index[category.category] = idx
        else:
            raise ValueError(f"my.cat:{lineno}: unrecognized line format: {raw_line!r}")

    for relation in relations:
        feat_type = relation_feature_type(relation.feature_set)
        term = " ".join(
            t
            for t in relation.tiers[0][0].split(" ")
            if t not in relation.feature_set.split("_")
        )
        base_term = term.removeprefix("~").removeprefix("and ").strip()

        merge_key = (feat_type, base_term, None) if term else None

        if merge_key and (idx := merge_index.get(merge_key)) is None:
            features.append(
                HeraldicFeature(feature_type=feat_type, subtype="", details=base_term)
            )
            idx = len(features) - 1
            if merge_key:
                merge_index[merge_key] = idx

        features[idx].codes[relation.feature_set] = term
        if not term.startswith("~"):
            _index_term(term_index, term, idx)

    for reference in cross_references:
        if reference.see_also or reference.term == "point":
            continue
        ref_parts = _cat_parts(reference.term)
        if len(ref_parts) == 2 and ref_parts[1] == "sea":
            terms = [f"sea {ref_parts[0]}", f"sea-{ref_parts[0]}", f"sea{ref_parts[0]}"]
        else:
            term = _category_term(ref_parts)
            terms = [term] if term else []
        if not terms:
            continue
        for target in reference.targets:
            idx = category_index.get(target)
            if idx is None:
                idx = category_index.get(", ".join(_cat_parts(target)))
            if idx is not None:
                for term in terms:
                    _index_term(term_index, term, idx)

    _add_extra_term_aliases(category_index, term_index)
    _add_plural_keys(features, term_index)
    _add_count_word_terms(term_index)
    _add_group_participle_terms(term_index)
    _add_division_tags(features, term_index)
    _add_peripheral_subtype(features, category_index)
    seme_fallback_code = _add_seme_features(
        features, category_index, term_index, cross_references
    )

    return FeatureCatalog(
        relations=relations,
        features=features,
        term_index=term_index,
        category_index=category_index,
        seme_fallback_code=seme_fallback_code,
        creature_subtypes=list(_HERALDIC_KNOWLEDGE.get("creature_subtypes", [])),
        preferred_ambiguous_codes=list(
            _HERALDIC_KNOWLEDGE.get("preferred_ambiguous_codes", [])
        ),
    )


def parse_catalog_file(src: Path) -> FeatureCatalog:
    return parse_catalog(src.read_text(encoding="utf-8"))


def save_catalog(catalog: FeatureCatalog, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(asdict(catalog), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_catalog(src: Path) -> FeatureCatalog:
    data = json.loads(src.read_text(encoding="utf-8"))
    return FeatureCatalog(
        relations=[FeatureRelation(**r) for r in data["relations"]],
        features=[HeraldicFeature(**f) for f in data["features"]],
        term_index=data["term_index"],
        category_index=data["category_index"],
        seme_fallback_code=data.get("seme_fallback_code", ""),
        creature_subtypes=data.get("creature_subtypes", []),
        preferred_ambiguous_codes=data.get("preferred_ambiguous_codes", []),
    )
