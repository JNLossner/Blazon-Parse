"""Line-generation regression tests for blazon_lines.py.

Targets parity with the old build_blazon()/search_terms() pipeline, not full
ground-truth matching - old itself doesn't hit that yet either. Expected
values verified directly against build_blazon()'s real output (see the
"Comparing pipelines" session notes), not guessed from ground truth.
"""

from pathlib import Path

import pytest

from blazon_parse.blazon_grammar import parse_blazon
from blazon_parse.blazon_lines import blazon_lines, grouped_blazon_lines
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
    tree = parse_blazon(
        blazon, tinctures=tinctures, divisions=divisions, treatments=treatments
    )
    return resolve_blazon(tree, catalog)


def lines_for(catalog: FeatureCatalog, blazon: str) -> set[str]:
    return set(blazon_lines(resolve(catalog, blazon)))


def test_field_division_translation(catalog: FeatureCatalog) -> None:
    """ "per X" divisions get a translated "divided Xwise" line alongside the
    coded division line."""
    lines = lines_for(catalog, "Per bend azure and gules, a lion sable.")
    assert "PB:azure:~and gules" in lines
    assert "FIELD:divided bendwise:~ azure:~and gules" in lines


def test_field_treatment_tincture_pairing(catalog: FeatureCatalog) -> None:
    """A field treatment's own second tincture (e.g. the ermine spots' color
    in "ermined vert") pairs onto the treatment's line, not just the field's
    own base tincture alone."""
    lines = lines_for(
        catalog,
        "Argent ermined vert, a beaver sejant erect proper maintaining a "
        "threaded needle sable.",
    )
    assert "FIELD TREATMENT-SEME (ERMINED):argent:~and vert" in lines


def test_semy_named_variant(catalog: FeatureCatalog) -> None:
    """A named semy variant ("semy-de-lys") already carries its charge code
    from the catalog and needs no completion - it surfaces as its own charge
    line plus the treatment line, with the bare field tincture lines still
    present (semy is a field pattern, not a division/treatment replacing the
    field's own identity)."""
    lines = lines_for(
        catalog,
        "Argent semy-de-lys azure, a catamount queue-fourchy passant and on "
        "a chief sable three mullets of six points argent.",
    )
    assert "FDL:azure:seme:seme on field" in lines
    assert "FIELD TREATMENT-SEME (DE-LYS):azure" in lines
    assert "AR" in lines
    assert "FIELD:argent:solid" in lines


def test_semy_generic_variant(catalog: FeatureCatalog) -> None:
    """A generic semy pattern with no named catalog variant ("semy of
    acorns") needs its charge and tincture discovered from what follows in
    the blazon text, same as build_blazon()'s complete_seme_feature."""
    lines = lines_for(
        catalog, "Argent semy of acorns proper, a reremouse sable incensed proper."
    )
    assert "FRUIT-NUT,ACORN:proper:seme:seme on field" in lines
    assert "FIELD TREATMENT-SEME (9OTHER):proper" in lines


def test_grouped_output_labels_by_charge(catalog: FeatureCatalog) -> None:
    """Groups are labeled by charge (host and related, each on their own),
    not by primary/secondary/tertiary rank - and still cover the exact same
    lines as the flat output, just reorganized."""
    resolved = resolve(
        catalog,
        "Argent, a cat couchant guardant, on a bordure sable, three mullets argent.",
    )
    groups = grouped_blazon_lines(resolved)
    by_label = {g.label: g.terms for g in groups}

    assert by_label["Field"] == ["AR", "FIELD:argent:solid"]
    assert by_label["cat couchant guardant"] == ["CAT:1:sable:primary:couchant"]
    assert by_label["bordure"] == ["BORDURE:1:sable:charged"]
    assert by_label["mullets"] == ["STAR:3:argent:tertiary"]

    all_grouped_terms = {term for g in groups for term in g.terms}
    assert all_grouped_terms == lines_for(
        catalog,
        "Argent, a cat couchant guardant, on a bordure sable, three mullets argent.",
    )


def test_grouped_output_gives_arrangement_its_own_group(
    catalog: FeatureCatalog,
) -> None:
    """A group-level arrangement line (addorsed, in annulo, ...) isn't tied
    to one specific charge, so it needs a group of its own rather than being
    silently dropped or misattributed."""
    resolved = resolve(catalog, "Sable, two lions statant addorsed Or.")
    groups = grouped_blazon_lines(resolved)
    by_label = {g.label: g.terms for g in groups}

    assert by_label["lions statant addorsed"] == ["CAT:2:or:primary:statant"]
    assert "ARRANGEMENT9BEAST&MONSTER,ADDORSED:or:primary" in [
        term for terms in by_label.values() for term in terms
    ]
