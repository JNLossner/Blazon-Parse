from blazon_parse.blazon_parser import resolve_feature_candidates
from blazon_parse.blazon_resolved import (
    ResolvedBlazon,
    ResolvedCharge,
    ResolvedField,
    ResolvedRelation,
)
from blazon_parse.blazon_tree import BlazonTree, ChargeNode, FieldNode, Relation
from blazon_parse.feature_catalog import FeatureCatalog
from blazon_parse.heraldic import FeatureType, HeraldicFeature
from blazon_parse.matcher import find_catalog_matches

_STRUCTURAL_RELATION_TAGS = {"on": "tertiary", "between": "second", "within": "second"}

# Which of "maintained"/"sustained"/"held" applies is a subjective judgment
# call (relative size of the charge vs. its holder) - confirmed against real
# armory descriptions: the same object ("sword") gets tagged both ways across
# different real examples for the same blazon wording. Not recoverable from
# text, so collapse to the generic "held" tier my.cat rolls all three into
# (held<secondary<second; maintained<held; sustained<held) rather than guess.
_HELD_FAMILY = {"maintained", "sustained", "held"}


def resolve_content(content: str, catalog: FeatureCatalog) -> list[HeraldicFeature]:
    matches = find_catalog_matches(content, catalog)
    features = []
    for span in sorted(matches):
        features.extend(resolve_feature_candidates(matches[span]))
    return features


def resolve_tinctures(
    tinctures: list[str], catalog: FeatureCatalog
) -> list[HeraldicFeature]:
    features = []
    for term in tinctures:
        candidates = [
            f for f in catalog[term] if f.feature_type == FeatureType.tincture
        ]
        features.extend(resolve_feature_candidates(candidates))
    return features


def resolve_count(count: str | None, catalog: FeatureCatalog) -> HeraldicFeature | None:
    if count is None:
        return None
    candidates = [f for f in catalog[count] if f.feature_type == FeatureType.count]
    resolved = resolve_feature_candidates(candidates)
    return resolved[0] if resolved else None


def resolve_relation_tag(keyword: str, catalog: FeatureCatalog) -> str:
    if keyword in _STRUCTURAL_RELATION_TAGS:
        return _STRUCTURAL_RELATION_TAGS[keyword]
    for feature in catalog[keyword]:
        if feature.feature_type == FeatureType.group:
            term = feature.search_term() or "tertiary"
            return "held" if term in _HELD_FAMILY else term
    return "tertiary"


def resolve_relation(relation: Relation, catalog: FeatureCatalog) -> ResolvedRelation:
    return ResolvedRelation(
        tag=resolve_relation_tag(relation.keyword, catalog),
        charged=relation.keyword != "between",
        charges=[resolve_charge(c, catalog) for c in relation.charges],
    )


def resolve_charge(node: ChargeNode, catalog: FeatureCatalog) -> ResolvedCharge:
    return ResolvedCharge(
        content=node.content,
        count=resolve_count(node.count, catalog),
        features=resolve_content(node.content, catalog),
        tinctures=resolve_tinctures(node.tinctures, catalog),
        relations=[resolve_relation(r, catalog) for r in node.relations],
    )


def resolve_field(field: FieldNode, catalog: FeatureCatalog) -> ResolvedField:
    if field.fieldless:
        return ResolvedField(features=list(catalog["fieldless"]))

    features = []
    if field.division:
        features.extend(resolve_feature_candidates(catalog[field.division]))
    content = field.modifiers[0] if field.modifiers else ""
    features.extend(resolve_content(content, catalog))

    return ResolvedField(
        content=content,
        features=features,
        tinctures=resolve_tinctures(field.tinctures, catalog),
    )


def resolve_blazon(tree: BlazonTree, catalog: FeatureCatalog) -> ResolvedBlazon:
    return ResolvedBlazon(
        field=resolve_field(tree.field, catalog),
        charge_groups=[
            [resolve_charge(c, catalog) for c in group] for group in tree.charge_groups
        ],
    )
