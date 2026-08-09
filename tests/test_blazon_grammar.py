"""Blazon-to-tree grammar regression tests.

Exercises `parse_blazon()` on real (and near-real) blazon text with a small
hardcoded tincture/division/treatment vocabulary, standing in for whatever
`feature_catalog`-backed lists get passed at runtime once that wiring exists.
Blazon text is drawn from `tests/data/oanda_examples.json` where noted.
"""

import pytest

from blazon_parse.blazon_grammar import parse_blazon
from blazon_parse.blazon_tree import BlazonTree, ChargeNode, FieldNode, Relation

TINCTURES = ["argent", "sable", "gules", "azure", "or", "vert", "purpure", "ermine"]
DIVISIONS = [
    "per pale",
    "per bend",
    "per bend sinister",
    "per fess",
    "per chevron",
    "per saltire",
    "per pall inverted",
    "quarterly",
]
TREATMENTS = ["ermined", "masoned", "semy"]


def parse(
    blazon: str,
    *,
    tinctures: list[str] = TINCTURES,
    divisions: list[str] = DIVISIONS,
    treatments: list[str] = TREATMENTS,
) -> BlazonTree:
    return parse_blazon(
        blazon, tinctures=tinctures, divisions=divisions, treatments=treatments
    )


def test_field_tincture_and_between_relation() -> None:
    tree = parse(
        "Argent, a cat couchant guardant between three mullets sable, "
        "a chief triangular gules."
    )
    assert tree.field == FieldNode(tinctures=["argent"])
    cat, chief = tree.charge_groups[0][0], tree.charge_groups[1][0]
    assert cat.content == "cat couchant guardant"
    assert cat.relations == [
        Relation(
            keyword="between",
            charges=[ChargeNode(count="three", content="mullets", tinctures=["sable"])],
        )
    ]
    assert chief.content == "chief triangular"
    assert chief.tinctures == ["gules"]


def test_field_treatment_and_maintaining_relation() -> None:
    tree = parse(
        "Argent ermined vert, a beaver sejant erect proper maintaining "
        "a threaded needle sable."
    )
    assert tree.field.tinctures == ["argent"]
    assert tree.field.modifiers == ["ermined vert"]
    beaver = tree.charge_groups[0][0]
    assert beaver.content == "beaver sejant erect proper"
    assert beaver.relations == [
        Relation(
            keyword="maintaining",
            charges=[
                ChargeNode(count="a", content="threaded needle", tinctures=["sable"])
            ],
        )
    ]


def test_division_with_and_joined_tinctures() -> None:
    tree = parse("Per bend azure and or, a lion sable.")
    assert tree.field.division == "per bend"
    assert tree.field.tinctures == ["azure", "or"]
    assert tree.charge_groups == [
        [ChargeNode(count="a", content="lion", tinctures=["sable"])]
    ]


def test_division_with_oxford_comma_joined_tinctures() -> None:
    """A 3+ tincture list uses commas between all but the last pair, not just 'and'."""
    tree = parse(
        "Per pall inverted azure, purpure, and argent, two edelweiss flowers "
        "argent and a Maltese cross sable."
    )
    assert tree.field.division == "per pall inverted"
    assert tree.field.tinctures == ["azure", "purpure", "argent"]
    assert tree.charge_groups == [
        [
            ChargeNode(count="two", content="edelweiss flowers", tinctures=["argent"]),
            ChargeNode(count="a", content="maltese cross", tinctures=["sable"]),
        ]
    ]


@pytest.mark.xfail(
    reason="Commas are used for more than field/charge-clause boundaries. "
    "In this example, they separate a single hawk's attributes (posture, "
    "wing position, tincture note), so every comma wrongly ends the current "
    "clause and fragments this into six charge groups, several empty. Also "
    "demonstrates a second bug: 'rising' is a real posture word but misfires "
    "as a bare-gerund relation with an empty target.",
    strict=True,
)
def test_hawk_with_comma_separated_attributes() -> None:
    tree = parse(
        "Argent, on a bend sinister doubly cotised azure, a hawk rising, "
        "wings displayed and inverted, and an increscent, both palewise, argent."
    )
    assert len(tree.charge_groups) == 1
    bend = tree.charge_groups[0][0]
    assert bend.content == "bend sinister doubly cotised"
    hawk = bend.relations[0].charges[0]
    assert hawk.content == "hawk rising"


def test_fieldless_parenthetical_prefix_with_fronted_on() -> None:
    tree = parse("(Fieldless) On a tree couped Or a dragonfly sable.")
    assert tree.field.fieldless is True
    tree_charge = tree.charge_groups[0][0]
    assert tree_charge.content == "tree couped"
    assert tree_charge.tinctures == ["or"]
    assert tree_charge.relations == [
        Relation(
            keyword="on",
            charges=[ChargeNode(count="a", content="dragonfly", tinctures=["sable"])],
        )
    ]


def test_fieldless_comma_prefix() -> None:
    tree = parse("Fieldless, a rose gules.")
    assert tree.field.fieldless is True
    assert tree.charge_groups == [
        [ChargeNode(count="a", content="rose", tinctures=["gules"])]
    ]


def test_and_within_continues_the_current_host() -> None:
    """Real pattern from the SCA armorial ('...tailed and within a bordure
    ...', '...fructed and within an orle...') - unlike 'on', 'within' is
    trailing-only in every 'and within' occurrence checked, so it should
    continue the current charge's relations rather than start a fresh one."""
    tree = parse("Argent, a seagoat tailed and within a bordure vert.")
    seagoat = tree.charge_groups[0][0]
    assert seagoat.content == "seagoat tailed"
    assert seagoat.relations == [
        Relation(
            keyword="within",
            charges=[ChargeNode(count="a", content="bordure", tinctures=["vert"])],
        )
    ]


@pytest.mark.parametrize(
    "blazon,expected_content",
    [
        ("Argent, a wing gules.", "wing"),
        ("Argent, a battering ram sable.", "battering ram"),
        ("Argent, a drinking horn sable.", "drinking horn"),
        ("Argent, a lightning bolt argent.", "lightning bolt"),
    ],
)
def test_ing_shaped_charge_names_are_not_mistaken_for_relations(
    blazon: str, expected_content: str
) -> None:
    """Real my.cat charge names whose first word ends in "-ing" - the
    bare-gerund relation rule must not fire on a charge's opening word."""
    charge = parse(blazon).charge_groups[0][0]
    assert charge.content == expected_content
    assert charge.relations == []


def test_and_on_after_a_charge_starts_a_fresh_sibling() -> None:
    tree = parse(
        "Argent semy-de-lys azure, a catamount queue-fourchy passant "
        "and on a chief sable three mullets argent."
    )
    catamount, chief = tree.charge_groups[0]
    assert catamount.relations == []
    assert chief.content == "chief"
    assert chief.tinctures == ["sable"]
    assert chief.relations == [
        Relation(
            keyword="on",
            charges=[
                ChargeNode(count="three", content="mullets", tinctures=["argent"])
            ],
        )
    ]


def test_and_chained_relation_attaches_to_the_outer_host() -> None:
    tree = parse(
        "(Fieldless) Two dolphins haurient respectant azure gorged of comital "
        "coronets and maintaining between them a rose Or."
    )
    dolphins = tree.charge_groups[0][0]
    assert [r.keyword for r in dolphins.relations] == ["gorged of", "maintaining"]
    gorged_of = next(r for r in dolphins.relations if r.keyword == "gorged of")
    assert gorged_of.charges == [ChargeNode(content="comital coronets")]
    maintaining = next(r for r in dolphins.relations if r.keyword == "maintaining")
    assert maintaining.charges == [
        ChargeNode(content="between them a rose", tinctures=["or"])
    ]
