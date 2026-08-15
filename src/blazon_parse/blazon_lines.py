from dataclasses import replace

from blazon_parse.blazon_resolved import ResolvedBlazon, ResolvedCharge, ResolvedField
from blazon_parse.heraldic import FeatureType, HeraldicFeature


def _tags(*features: HeraldicFeature | None) -> list[str]:
    return [term for f in features if f is not None and (term := f.search_term())]


def _tincture_tags(
    tincture: HeraldicFeature | None, secondary: HeraldicFeature | None
) -> list[str]:
    secondary_term = secondary.search_term(scope="tincture2") if secondary else None
    primary_term = (
        tincture.search_term(scope=("tincture1" if secondary_term else "tincture"))
        if tincture
        else None
    )
    return [t for t in (primary_term, secondary_term) if t]


def _line(code: str, tags: list[str]) -> str:
    return ":".join([code, *tags])


def _identity_and_modifiers(
    charge: ResolvedCharge,
) -> tuple[HeraldicFeature | None, list[HeraldicFeature]]:
    charge_features = [
        f for f in charge.features if f.feature_type == FeatureType.charge
    ]
    modifiers = [f for f in charge.features if f.feature_type != FeatureType.charge]
    identity = charge_features[0] if charge_features else None
    return identity, modifiers


def charge_lines(charge: ResolvedCharge, rank_tag: str | None) -> list[str]:
    identity, modifiers = _identity_and_modifiers(charge)
    if identity is None:
        return []
    code = identity.search_term()
    if not code:
        return []

    tincture = charge.tinctures[0] if charge.tinctures else None
    secondary_tincture = charge.tinctures[1] if len(charge.tinctures) > 1 else None
    shared_tags = [
        *_tags(charge.count),
        *_tincture_tags(tincture, secondary_tincture),
        *([rank_tag] if rank_tag else []),
    ]

    coded_modifiers = []
    plain_modifiers = []
    for modifier in modifiers:
        if modifier.feature_type == FeatureType.arrangement:
            continue
        if modifier.feature_type == FeatureType.charge_treatment and modifier.code:
            coded_modifiers.append(modifier)
        else:
            plain_modifiers.append(modifier)

    charged = any(r.charged for r in charge.relations)
    charge_tags = [*shared_tags, *_tags(*plain_modifiers)]
    if charged:
        charge_tags.append("charged")

    lines = [_line(code, charge_tags)]
    lines.extend(_line(m.search_term(), shared_tags) for m in coded_modifiers)

    for relation in charge.relations:
        lines.extend(group_lines(relation.charges, relation.tag))

    return lines


def _uniform_tincture(charges: list[ResolvedCharge]) -> HeraldicFeature | None:
    tinctures = []
    for charge in charges:
        if len(charge.tinctures) != 1:
            return None
        tinctures.append(charge.tinctures[0])
    terms = {t.search_term() for t in tinctures}
    return tinctures[0] if len(terms) == 1 else None


def group_lines(charges: list[ResolvedCharge], rank_tag: str | None) -> list[str]:
    lines = []
    for charge in charges:
        lines.extend(charge_lines(charge, rank_tag))

    arrangement_features = [
        f
        for c in charges
        for f in c.features
        if f.feature_type == FeatureType.arrangement and f.code
    ]
    if arrangement_features:
        tincture = _uniform_tincture(charges)
        group_tags = [
            *(_tincture_tags(tincture, None) if tincture else []),
            *([rank_tag] if rank_tag else []),
        ]
        for feature in arrangement_features:
            lines.append(_line(feature.search_term(), group_tags))

    return lines


def _complete_seme(
    treatment: HeraldicFeature, field_features: list[HeraldicFeature]
) -> HeraldicFeature:
    """Fill in a generic "semy of X" marker's charge and/or tincture from
    whatever charge/tincture terms the field's own content resolved to - a
    named variant ("semy-de-lys") already carries its charge code from the
    catalog and skips this."""
    codes = dict(treatment.codes)
    for feature in field_features:
        if feature.feature_type not in (FeatureType.charge, FeatureType.tincture):
            continue
        key = "charge" if feature.feature_type == FeatureType.charge else "tincture"
        if key in codes:
            continue
        codes[key] = feature.search_term(
            scope="tincture" if key == "tincture" else None
        )
    return replace(treatment, codes=codes)


def field_lines(field: ResolvedField) -> list[str]:
    division = next(
        (f for f in field.features if f.feature_type == FeatureType.field_division),
        None,
    )
    treatment = next(
        (f for f in field.features if f.feature_type == FeatureType.field_treatment),
        None,
    )
    content_tincture = next(
        (f for f in field.features if f.feature_type == FeatureType.tincture), None
    )
    line = next((f for f in field.features if f.feature_type == FeatureType.line), None)

    tincture = field.tinctures[0] if field.tinctures else None
    secondary_tincture = (
        field.tinctures[1] if len(field.tinctures) > 1 else content_tincture
    )

    is_seme = treatment is not None and treatment.subtype == "seme"
    if is_seme:
        treatment = _complete_seme(treatment, field.features)

    tincture_tags = _tincture_tags(tincture or treatment, secondary_tincture)
    bare_primary_tags = [t.removeprefix("~ ") for t in tincture_tags]
    division_tags = [*bare_primary_tags, *_tags(line)]

    division_coded = division is not None and bool(division.code)
    treatment_coded = treatment is not None and bool(treatment.code)

    lines = []
    if not division_coded and (not treatment_coded or is_seme) and tincture:
        lines.append(tincture.search_term(scope="field"))
        lines.append(tincture.search_term(scope="FIELD"))

    if division_coded:
        lines.append(_line(division.search_term(), division_tags))
        if "divided" in division.codes:
            lines.append(
                _line(
                    "FIELD", [division.codes["divided"], *tincture_tags, *_tags(line)]
                )
            )

    if not treatment_coded:
        return lines

    if not is_seme:
        lines.append(_line(treatment.search_term(), bare_primary_tags))
        if "FIELD" in treatment.codes:
            lines.append(treatment.search_term(scope="FIELD"))
    else:
        seme_tag = treatment.codes.get("tincture")
        seme_tags = [seme_tag] if seme_tag else []
        if charge_code := treatment.codes.get("charge"):
            lines.append(_line(charge_code, [*seme_tags, "seme", "seme on field"]))
        lines.append(_line(treatment.search_term(), seme_tags))

    return lines


def blazon_lines(blazon: ResolvedBlazon) -> list[str]:
    lines = field_lines(blazon.field)
    if not blazon.charge_groups:
        lines.append("FO")
    for group in blazon.charge_groups:
        is_peripheral = any(
            f.subtype == "peripheral"
            for charge in group
            for f in charge.features
            if f.feature_type == FeatureType.charge
        )
        rank_tag = None if is_peripheral else "primary"
        lines.extend(group_lines(group, rank_tag))
    return lines
