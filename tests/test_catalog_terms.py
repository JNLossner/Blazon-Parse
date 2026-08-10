"""Term -> catalog code regression tests.

Targets `FeatureCatalog` directly (term_index/feature resolution) rather than
full blazon parsing, so a case here pins down exactly which catalog term is
misrouted instead of a whole-sentence diff.
"""

import json
from pathlib import Path

import pytest

from blazon_parse.blazon_parser import build_blazon, grouped_search_terms
from blazon_parse.feature_catalog import FeatureCatalog, parse_catalog_file

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "my.cat"
KNOWLEDGE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "blazon_parse"
    / "heraldic_knowledge.json"
)


@pytest.fixture(scope="session")
def catalog() -> FeatureCatalog:
    return parse_catalog_file(CATALOG_PATH)


def codes_for(catalog: FeatureCatalog, term: str) -> set[str]:
    return {code for f in catalog[term] if (code := f.code)}


# Every one of these is a synonym for "roundel, whole" in my.cat and must
# carry the ROUNDEL code, not whichever unrelated ", whole" category happened
# to be parsed first (previously BIRD, from "bird, whole").
ROUNDEL_FAMILY = [
    "roundel",
    "roundelly",
    "bezant",
    "bezanty",
    "fountain",
    "pomme",
    "plate",
    "platy",
    "torteau",
    "hurt",
    "pellet",
    "pellety",
    "ogress",
    "golpe",
    "gunstone",
]


@pytest.mark.parametrize("term", ROUNDEL_FAMILY)
def test_roundel_family_resolves_to_roundel(catalog: FeatureCatalog, term: str) -> None:
    assert "ROUNDEL" in codes_for(catalog, term)
    assert "BIRD" not in codes_for(catalog, term)


# Named gouttes ("goutte de sang" etc.) aren't in my.cat at all.
# The "goutte de X": ["goute"] entries in extra_term_aliases
# make them resolve to the generic goutte charge code.
GOUTTE_FAMILY = [
    "goutte de sang",
    "goutte d'eau",
    "goutte de larmes",
    "goutte d'or",
    "goutte de vin",
    "goutte de poix",
    "goutte de huix",
    "goutte d'olive",
]


@pytest.mark.parametrize("term", GOUTTE_FAMILY)
def test_goutte_family_resolves_to_goute(catalog: FeatureCatalog, term: str) -> None:
    assert "GOUTE" in codes_for(catalog, term)


def test_bird_whole_still_resolves_to_bird(catalog: FeatureCatalog) -> None:
    """The merge fix must not have swung the bug the other way."""
    idx = catalog.category_index["bird, whole"]
    assert catalog.features[idx].code == "BIRD"


@pytest.mark.parametrize(
    "category,expected_code",
    [
        ("cross, throughout", "CROSS"),
        ("saltire, throughout", "SALTIRE"),
    ],
)
def test_throughout_categories_keep_their_own_code(
    catalog: FeatureCatalog, category: str, expected_code: str
) -> None:
    """ "cross, throughout" and "saltire, throughout" must not merge into one
    feature by way of the shared, non-distinguishing "throughout" term."""
    idx = catalog.category_index[category]
    assert catalog.features[idx].code == expected_code


def test_bare_throughout_is_not_a_search_term(catalog: FeatureCatalog) -> None:
    """ "throughout" is a standalone field-position attribute, not itself a
    charge name - it should never resolve to a charge code on its own,
    the same way "other" doesn't."""
    assert "throughout" not in catalog.term_index


# "demi" legitimately carries a different code per governing charge type -
# unlike "whole"/"throughout", these lines are meant to merge into one
# feature, keyed by subtype.
DEMI_CODES = {
    "beast": "BEAST9DEMI",
    "bird": "BIRD9DEMI",
    "monster": "MONSTER9DEMI",
    "roundel": "ROUNDEL-DEMI",
    "sun": "SUN-DEMI",
}


def test_demi_merges_all_governing_types_into_one_feature(
    catalog: FeatureCatalog,
) -> None:
    features = catalog["demi"]
    assert len(features) == 1
    assert features[0].codes == DEMI_CODES


# Known, not-yet-fixed gap: "strawberry" collides between "fruit, strawberry"
# and "plant, strawberry".
@pytest.mark.xfail(reason="fruit/plant term collision not yet resolved", strict=True)
def test_strawberry_plant_is_reachable(catalog: FeatureCatalog) -> None:
    assert "PLANT-STRAWBERRY" in codes_for(catalog, "strawberry")


def test_bare_saltire_reaches_a_real_code(catalog: FeatureCatalog) -> None:
    assert codes_for(catalog, "saltire") & {"SALTIRE", "SALTIRE*9"}


def _codes_in_groups(catalog: FeatureCatalog, blazon: str) -> set[str]:
    groups = grouped_search_terms(build_blazon(blazon, catalog))
    return {t.split(":")[0] for g in groups for t in g.terms}


# There's no reliable textual signal to pick ordinary-form vs charge-form -
# both codes come back so the user can choose.
def test_cross_is_ambiguous_between_ordinary_and_charge(
    catalog: FeatureCatalog,
) -> None:
    codes = _codes_in_groups(catalog, "Fieldless, a cross argent.")
    assert {"CROSS", "CRAC"} <= codes


def test_saltire_is_ambiguous_between_ordinary_and_charge(
    catalog: FeatureCatalog,
) -> None:
    codes = _codes_in_groups(catalog, "Fieldless, a saltire argent.")
    assert {"SALTIRE", "SALTIRE*9"} <= codes


# Preparation for implied features (e.g. "a bezant" means "a roundel or" -
# the tincture is baked into the charge name, not stated separately). Loaded
# straight from heraldic_knowledge.json.
IMPLIED_FEATURES: dict[str, str] = json.loads(
    KNOWLEDGE_PATH.read_text(encoding="utf-8")
)["implied_features"]

# Plain-tincture cases only - "fountain"'s multicolor pattern is more than
# one tag piece, so it's checked separately below.
SOLID_IMPLIED_TINCTURES = {
    term: tag for term, tag in IMPLIED_FEATURES.items() if ":" not in tag
}


def _own_charge_line(
    catalog: FeatureCatalog, term: str, terms: list[str]
) -> str | None:
    """The output line for `term`'s own resolved code (ROUNDEL, GOUTE, ...) -
    never the field's, even when the field tincture happens to equal the
    term's implied one (e.g. "plate" implies argent, same as the field
    below)."""
    code = next(iter(codes_for(catalog, term)), None)
    return next((t for t in terms if code and t.startswith(code)), None)


@pytest.mark.parametrize("term,tincture", SOLID_IMPLIED_TINCTURES.items())
@pytest.mark.xfail(
    reason="implied tincture not yet applied when the blazon omits one", strict=True
)
def test_untinctured_charge_gets_implied_tincture(
    catalog: FeatureCatalog, term: str, tincture: str
) -> None:
    blazon_struct = build_blazon(f"Argent, a {term}.", catalog)
    charge_line = _own_charge_line(catalog, term, blazon_struct.search_terms())
    assert charge_line is not None
    assert tincture in charge_line.split(":")


@pytest.mark.xfail(
    reason="fountain's implied multicolor pattern is not yet applied when "
    "the blazon omits an explicit tincture",
    strict=True,
)
def test_untinctured_fountain_gets_implied_pattern(catalog: FeatureCatalog) -> None:
    blazon_struct = build_blazon("Argent, a fountain.", catalog)
    charge_line = _own_charge_line(catalog, "fountain", blazon_struct.search_terms())
    assert charge_line is not None
    for tag in IMPLIED_FEATURES["fountain"].split(":"):
        assert tag in charge_line.split(":")
