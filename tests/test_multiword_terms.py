"""Multi-word blazon phrase regression tests.

These exercise full `build_blazon()` on short blazons where a charge name
is itself two words, or is qualified by an adjacent word (a body part, a species)
that should change which code wins. Several are known-broken; see each xfail
reason for the specific my.cat lines involved.
"""

from pathlib import Path

import pytest

from blazon_parse.blazon_parser import build_blazon
from blazon_parse.feature_catalog import FeatureCatalog, parse_catalog_file

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "my.cat"


@pytest.fixture(scope="session")
def catalog() -> FeatureCatalog:
    return parse_catalog_file(CATALOG_PATH)


def terms_for(catalog: FeatureCatalog, blazon: str) -> list[str]:
    return build_blazon(blazon, catalog).search_terms()


def test_laurel_wreath_resolves_to_laurel_wreath_code(catalog: FeatureCatalog) -> None:
    """Baseline: "wreath, laurel|LW" already works."""
    terms = terms_for(catalog, "Argent, a laurel wreath vert.")
    assert any(t.startswith("LW") for t in terms)


@pytest.mark.xfail(
    reason="'wreath, not laurel' contributes no term of its own."
    "'holly wreath' has no alias, so 'holly' matches and 'wreath' is dropped",
    strict=True,
)
def test_holly_wreath_resolves_to_wreath_code(catalog: FeatureCatalog) -> None:
    terms = terms_for(catalog, "Argent, a holly wreath azure.")
    assert any(t.startswith("WREATH,OTHER") for t in terms)
    assert any(t.startswith("PLANT-HOLLY") for t in terms)


@pytest.mark.xfail(
    reason="'an oak sprig' resolves as a whole tree "
    "(TREE-ROUNDED SHAPE) instead of PLANT-SPRIG - the tree-branch tag "
    "('fructed of three') already comes through correctly",
    strict=True,
)
def test_oak_sprig_resolves_to_plant_sprig(catalog: FeatureCatalog) -> None:
    terms = terms_for(catalog, "Fieldless, an oak sprig vert fructed of three or.")
    assert any(t.startswith("PLANT-SPRIG") for t in terms)
    assert any(t.startswith("TREE9BRANCH") for t in terms)


def test_tygers_head_keeps_specific_code_through_possessive(
    catalog: FeatureCatalog,
) -> None:
    """Already works - pinned so a future change to possessive/'s handling
    can't silently regress to a generic head code."""
    terms = terms_for(catalog, "Fieldless, a tyger's head.")
    assert any(t.startswith("HEAD-MONSTER,TYGER") for t in terms)


@pytest.mark.xfail(
    reason="'skull' doesn't use the adjacent creature word as context the "
    "way 'head' does for 'tyger's head' - 'bear' matches independently as "
    "the whole charge BEAST-BEAR, and bare 'skull' falls back to the "
    "preferred_ambiguous_codes default (HEAD-HUMAN SKULL) instead of the "
    "catalog's own 'head, beast, skull|HEAD-BEAST9SKULL'",
    strict=True,
)
def test_bear_skull_is_not_human(catalog: FeatureCatalog) -> None:
    terms = terms_for(catalog, "Or, a bear skull.")
    assert any(t.startswith("HEAD-BEAST9SKULL") for t in terms)
    assert not any(t.startswith("HEAD-HUMAN SKULL") for t in terms)
    assert not any(t.startswith("BEAST-BEAR") for t in terms)


@pytest.mark.xfail(
    reason="my.cat treats these as two different charges by spacing alone: "
    "'seahorse' (one word) is 'fish, seahorse|FISH-SEAHORSE' directly, "
    "while 'sea horse' (two words) aliases to 'monster, sea, horse' (the "
    "mythological hippocamp) per my.cat:3314 - matching FISH-SEAHORSE "
    "requires the extra qualifier 'natural' (my.cat:3315). Whether the fix "
    "is to normalize the spacing or treat both as ambiguous candidates is "
    "still open; this only pins that they currently disagree",
    strict=True,
)
def test_seahorse_spacing_does_not_change_the_code(catalog: FeatureCatalog) -> None:
    one_word = terms_for(catalog, "Fieldless, a seahorse azure.")
    two_word = terms_for(catalog, "Fieldless, a sea horse azure.")

    def charge_code(terms: list[str]) -> str | None:
        return next((t.split(":")[0] for t in terms if t not in ("NO", "FO")), None)

    assert charge_code(one_word) == charge_code(two_word)
