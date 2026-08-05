import json
from collections.abc import KeysView
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from blazon_parse.catalog_parser import (
    Category,
    CrossReference,
    FeatureRelation,
    _add_plural_keys,
    decode_daud,
)
from blazon_parse.heraldic import HeraldicFeature, to_feature_type


@dataclass
class FeatureCatalog:
    relations: list[FeatureRelation]
    features: list[HeraldicFeature]
    term_index: dict[str, list[int]]
    category_index: dict[str, int] = dataclass_field(default_factory=dict)

    def __getitem__(self, term: str) -> list[HeraldicFeature]:
        return [self.features[i] for i in self.term_index.get(term, [])]

    def terms(self) -> KeysView[str]:
        return self.term_index.keys()


def _index_term(term_index: dict[str, list[int]], term: str, idx: int) -> None:
    """Map term -> idx, skipping it if already mapped."""
    indices = term_index.setdefault(term, [])
    if idx not in indices:
        indices.append(idx)


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
            term = category.terms[0] if category.terms else None
            merge_key = (
                (category.heraldic.feature_type, term, category.kind) if term else None
            )
            if merge_key and (idx := merge_index.get(merge_key)) is not None:
                features[idx].codes.update(category.heraldic.codes)
            else:
                features.append(category.heraldic)
                idx = len(features) - 1
                if merge_key:
                    merge_index[merge_key] = idx
                if term:
                    _index_term(term_index, term, idx)
            category_index[category.category] = idx
        else:
            raise ValueError(f"my.cat:{lineno}: unrecognized line format: {raw_line!r}")

    for relation in relations:
        feat_type = to_feature_type(relation.feature_set)
        term = " ".join(
            t
            for t in relation.tiers[0][0].split(" ")
            if t not in relation.feature_set.split("_")
        )
        base_term = term.removeprefix("~").removeprefix("and ").strip()

        merge_key = (feat_type, base_term) if term else None

        if merge_key and (idx := merge_index.get(merge_key)) is None:
            features.append(
                HeraldicFeature(feature_type=feat_type, subtype="", details=base_term)
            )
            idx = len(features) - 1
            if merge_key:
                merge_index[merge_key] = idx

        features[idx].codes[relation.feature_set] = term
        _index_term(term_index, term, idx)

    for reference in cross_references:
        for target in reference.targets:
            if (idx := category_index.get(target)) is not None:
                _index_term(term_index, reference.term, idx)

    _add_plural_keys(term_index)

    return FeatureCatalog(
        relations=relations,
        features=features,
        term_index=term_index,
        category_index=category_index,
    )


def parse_catalog_file(src: Path) -> FeatureCatalog:
    return parse_catalog(src.read_text(encoding="utf-8"))


def save_catalog(catalog: FeatureCatalog, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(asdict(catalog), indent=2, ensure_ascii=False), encoding="utf-8"
    )
