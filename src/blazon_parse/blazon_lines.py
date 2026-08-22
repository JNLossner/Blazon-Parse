from dataclasses import replace

from blazon_parse.blazon_parser import TermGroup
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


def _shared_tags(charge: ResolvedCharge, rank_tag: str | None) -> list[str]:
    tincture = charge.tinctures[0] if charge.tinctures else None
    secondary_tincture = charge.tinctures[1] if len(charge.tinctures) > 1 else None
    return [
        *_tags(charge.count),
        *_tincture_tags(tincture, secondary_tincture),
        *([rank_tag] if rank_tag else []),
    ]


def ambiguous_charge_lines(charge: ResolvedCharge, rank_tag: str | None) -> list[str]:
    """Alternate lines for charge-type matches that lost out to another
    match in the same content (see `resolve_content`)."""
    shared_tags = _shared_tags(charge, rank_tag)
    return [
        _line(code, shared_tags)
        for alt in charge.ambiguous
        if (code := alt.search_term())
    ]


def own_charge_lines(charge: ResolvedCharge, rank_tag: str | None) -> list[str]:
    """This charge's own lines - code, tincture, count, modifiers - not
    including anything from its relations' charges."""
    identity, modifiers = _identity_and_modifiers(charge)
    if identity is None:
        return []
    code = identity.search_term()
    if not code:
        return []

    shared_tags = _shared_tags(charge, rank_tag)

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
    return lines


def charge_lines(charge: ResolvedCharge, rank_tag: str | None) -> list[str]:
    lines = own_charge_lines(charge, rank_tag)
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


def _arrangement_lines(
    charges: list[ResolvedCharge], rank_tag: str | None
) -> list[str]:
    """Lines for arrangement features (addorsed, in annulo, ...) shared by
    the whole sibling group - not tied to any one charge's own identity."""
    arrangement_features = [
        f
        for c in charges
        for f in c.features
        if f.feature_type == FeatureType.arrangement and f.code
    ]
    if not arrangement_features:
        return []
    tincture = _uniform_tincture(charges)
    group_tags = [
        *(_tincture_tags(tincture, None) if tincture else []),
        *([rank_tag] if rank_tag else []),
    ]
    return [_line(f.search_term(), group_tags) for f in arrangement_features]


def group_lines(charges: list[ResolvedCharge], rank_tag: str | None) -> list[str]:
    lines = []
    for charge in charges:
        lines.extend(charge_lines(charge, rank_tag))
    lines.extend(_arrangement_lines(charges, rank_tag))
    return lines


def charge_term_groups(
    charges: list[ResolvedCharge], rank_tag: str | None
) -> list[TermGroup]:
    """Charge-labeled groups (one per charge, host and related alike) rather
    than primary/secondary/tertiary rank groups - each holds just that
    charge's own lines, keyed by its raw content text."""
    groups = []
    for charge in charges:
        lines = own_charge_lines(charge, rank_tag)
        if lines:
            groups.append(
                TermGroup(
                    charge.content,
                    lines,
                    alternates=ambiguous_charge_lines(charge, rank_tag),
                )
            )
        for relation in charge.relations:
            groups.extend(charge_term_groups(relation.charges, relation.tag))
    arrangement_lines = _arrangement_lines(charges, rank_tag)
    if arrangement_lines:
        groups.append(TermGroup("Arrangement", arrangement_lines))
    return groups


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


def _group_rank_tag(group: list[ResolvedCharge]) -> str | None:
    is_peripheral = any(
        f.subtype == "peripheral"
        for charge in group
        for f in charge.features
        if f.feature_type == FeatureType.charge
    )
    return None if is_peripheral else "primary"


def blazon_lines(blazon: ResolvedBlazon) -> list[str]:
    lines = field_lines(blazon.field)
    if not blazon.charge_groups:
        lines.append("FO")
    for group in blazon.charge_groups:
        lines.extend(group_lines(group, _group_rank_tag(group)))
    return lines


def grouped_blazon_lines(blazon: ResolvedBlazon) -> list[TermGroup]:
    """Same content as blazon_lines(), reorganized into charge-labeled
    groups instead of one flat list - no primary/secondary/tertiary rank
    grouping, just "which charge did this line come from"."""
    field = field_lines(blazon.field)
    if not blazon.charge_groups:
        field = [*field, "FO"]
    groups = [TermGroup("Field", field)] if field else []
    for group in blazon.charge_groups:
        groups.extend(charge_term_groups(group, _group_rank_tag(group)))
    return groups
