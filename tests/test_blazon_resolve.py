"""Resolver regression tests for blazon_resolve.py."""

from pathlib import Path

import pytest

from blazon_parse.blazon_grammar import parse_blazon
from blazon_parse.blazon_resolve import resolve_blazon
from blazon_parse.feature_catalog import FeatureCatalog, parse_catalog_file
from blazon_parse.heraldic import FeatureType

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "my.cat"


@pytest.fixture(scope="session")
def catalog() -> FeatureCatalog:
    return parse_catalog_file(CATALOG_PATH)


def _terms_of(catalog: FeatureCatalog, feature_type: FeatureType) -> list[str]:
    return [
        term
        for term, idxs in catalog.term_index.items()
        if any(catalog.features[i].feature_type == feature_type for i in idxs)
    ]


def resolve(catalog: FeatureCatalog, blazon: str):
    tinctures = _terms_of(catalog, FeatureType.tincture)
    divisions = _terms_of(catalog, FeatureType.field_division)
    treatments = _terms_of(catalog, FeatureType.field_treatment)
    lines = _terms_of(catalog, FeatureType.line)
    tree = parse_blazon(
        blazon,
        tinctures=tinctures,
        divisions=divisions,
        treatments=treatments,
        lines=lines,
    )
    return resolve_blazon(tree, catalog)


def test_tincture_backfills_across_relations(catalog: FeatureCatalog) -> None:
    """A tincture with nothing else to attach to applies backward to every
    still-untinctured charge seen so far, even across different relations on
    the same host - real SCA blazon convention, matches the old pipeline's
    "unspecified charges" mechanism (any bare tincture match fills in every
    charge added so far that doesn't have one yet)."""
    resolved = resolve(
        catalog,
        "(Fieldless) Two dolphins hauriant respectant azure gorged of comital "
        "coronets and maintaining between them a rose Or.",
    )
    dolphins = resolved.charge_groups[0][0]
    assert [t.search_term() for t in dolphins.tinctures] == ["AZ"]

    gorged_of = next(r for r in dolphins.relations if r.tag == "tertiary")
    coronets = gorged_of.charges[0]
    assert [t.search_term() for t in coronets.tinctures] == ["OR"]

    held = next(r for r in dolphins.relations if r.tag == "held")
    rose = held.charges[0]
    assert [t.search_term() for t in rose.tinctures] == ["OR"]
