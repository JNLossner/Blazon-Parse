import string
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field

_PUNCTUATION_TO_SPACE = str.maketrans(string.punctuation, " " * len(string.punctuation))

from blazon_parse.feature_catalog import FeatureCatalog
from blazon_parse.heraldic import (
    FeatureType,
    HeraldicBlazon,
    HeraldicCharge,
    HeraldicChargeGroup,
    HeraldicFeature,
    HeraldicField,
)
from blazon_parse.matcher import find_catalog_matches


def _compute_unmatched(
    blazon: str, matches: dict[tuple[int, int], list[HeraldicFeature]]
) -> dict[tuple[int, int], str]:
    cleaned_blazon = blazon.translate(_PUNCTUATION_TO_SPACE)
    unmatched = [i for i, c in enumerate(cleaned_blazon) if c != " "]
    for start, end in matches:
        for i in range(start, end):
            try:
                unmatched.remove(i)
            except ValueError:
                pass

    unmatched_features: dict[tuple[int, int], str] = {}

    group: list[int] = []
    for i in unmatched:
        if not group or i == group[-1] + 1:
            group.append(i)
        else:
            span = (group[0], group[-1] + 1)
            unmatched_features[span] = blazon[span[0] : span[-1]]
            group.clear()
            group.append(i)
    if group:
        span = (group[0], group[-1] + 1)
        unmatched_features[span] = blazon[span[0] : span[-1]]

    return unmatched_features


def get_blazon_features(
    blazon: str, catalog: FeatureCatalog
) -> tuple[
    dict[tuple[int, int], list[HeraldicFeature]],
    dict[tuple[int, int], str],
]:
    matches = find_catalog_matches(blazon.lower(), catalog)
    unmatched = _compute_unmatched(blazon, matches)

    # A match glued to unmatched text with no separating space almost always
    # landed mid-word (e.g. "a" matching inside "and", "or" inside "gorged")
    for span in find_glued_matches(blazon, matches, unmatched):
        del matches[span]
    for span in find_hyphen_compound_prefixes(blazon, matches):
        del matches[span]
    unmatched = _compute_unmatched(blazon, matches)

    return matches, unmatched


def find_glued_matches(
    blazon: str,
    matches: dict[tuple[int, int], list[HeraldicFeature]],
    unmatched: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    """Match spans directly touching unmatched text."""
    unmatched_starts = {start for start, _ in unmatched}
    unmatched_ends = {end for _, end in unmatched}
    return sorted(
        span
        for span in matches
        if (span[0] in unmatched_ends) or (span[1] in unmatched_starts)
    )


def find_hyphen_compound_prefixes(
    blazon: str, matches: dict[tuple[int, int], list[HeraldicFeature]]
) -> list[tuple[int, int]]:
    """Charge matches shadowed by hyphenated compound adjectives ("bat-winged", "bull-headed")."""
    shadowed = []
    for pos, char in enumerate(blazon):
        if char != "-":
            continue
        prefix_span = next((s for s in matches if s[1] == pos), None)
        if prefix_span is None:
            continue
        if not any(f.feature_type == FeatureType.charge for f in matches[prefix_span]):
            continue
        suffix_end = pos + 1
        while suffix_end < len(blazon) and blazon[suffix_end].isalpha():
            suffix_end += 1
        suffix_text = blazon[pos + 1 : suffix_end].lower()
        if suffix_text.endswith(("ed", "ing")):
            shadowed.append(prefix_span)
    return shadowed


def resolve_feature_candidates(
    candidates: list[HeraldicFeature],
) -> list[HeraldicFeature]:
    """Same-span candidates worth keeping, folding in variant tags."""
    if not candidates:
        return []

    coded = [c for c in candidates if c.codes.get(c.subtype)]
    scoped = coded or candidates

    if tincture1 := [c for c in scoped if c.subtype == "tincture1"]:
        scoped = tincture1

    primary = scoped[0]

    if coded and primary.feature_type == FeatureType.charge and primary.details is None:
        variant = next(
            (
                c
                for c in candidates
                if c not in coded
                and c.feature_type == FeatureType.charge_treatment
                and c.search_term()
            ),
            None,
        )
        if variant is not None:
            scoped = [replace(primary, details=variant.search_term()), *scoped[1:]]

    return scoped


def resolve_feature(candidates: list[HeraldicFeature]) -> HeraldicFeature | None:
    """Pick the best candidate - for callers without deferred resolution."""
    scoped = resolve_feature_candidates(candidates)
    return scoped[0] if scoped else None


def resolve_field_feature(
    candidates: list[HeraldicFeature], field_features: list[HeraldicFeature]
) -> HeraldicFeature | None:
    if not field_features:
        candidates = [
            c
            for c in candidates
            if c.feature_type
            in (FeatureType.field_division, FeatureType.field_treatment)
            or (c.feature_type == FeatureType.tincture and "field" in c.codes)
        ]
    else:
        candidates = [
            c
            for c in candidates
            if c.feature_type in (FeatureType.field_treatment, FeatureType.line)
            or (c.feature_type == FeatureType.tincture and c.subtype != "field")
        ]

    return resolve_feature(candidates)


def build_field(field_features: list[HeraldicFeature]):
    tincture: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    division: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None
    line: HeraldicFeature | None = None

    for feat in field_features:
        if feat.feature_type == FeatureType.field_division:
            division = feat
        elif feat.feature_type == FeatureType.field_treatment:
            treatment = feat
        elif feat.feature_type == FeatureType.line:
            line = feat
        elif tincture is None:
            tincture = feat
        else:
            secondary_tincture = feat

    return HeraldicField(
        tincture=tincture or HeraldicFeature(FeatureType.tincture, "unknown"),
        division=division,
        secondary_tincture=secondary_tincture,
        treatment=treatment,
        line=line,
    )


def complete_seme_feature(
    treatment: HeraldicFeature,
    matches: dict[tuple[int, int], list[HeraldicFeature]],
    spans: list[tuple[int, int]],
) -> HeraldicFeature:
    """Fill in a "semy of X" marker's charge and/or tincture from the
    matches right after it, popping them from `matches`/`spans` in place.

    A named my.cat variant ("semy-de-lys") already carries its charge code
    from the catalog (see `_add_seme_features`) but still needs its own
    tincture, which - unlike every other field treatment - is independent of
    the field's own and would otherwise be mis-bucketed as a second field
    tincture by `build_field`. The generic fallback ("semy of acorns", no
    catalog alias for "acorn") needs its charge discovered the same way.
    """
    codes = dict(treatment.codes)
    for _ in range(2):
        if not spans:
            break
        feat = next(
            (
                f
                for f in matches[spans[0]]
                if f.feature_type in (FeatureType.charge, FeatureType.tincture)
            ),
            None,
        )
        if feat is None or feat.feature_type in codes:
            break
        scope = "tincture" if feat.feature_type == FeatureType.tincture else None
        codes[feat.feature_type] = feat.search_term(scope=scope)
        matches.pop(spans.pop(0))
    return replace(treatment, codes=codes)


@dataclass
class ChargeGroupBuilder:
    """Builds the 5 charge groups from `HeraldicBlazon`'s grammar (see its
    docstring) - primary, secondary-around-primary, tertiary-on-(2)-or-(3),
    peripheral secondary, and tertiary-on-peripheral. `current` tracks which
    of these the next unqualified charge lands in.
    """

    primary: HeraldicChargeGroup = dataclass_field(default_factory=HeraldicChargeGroup)
    secondary: HeraldicChargeGroup = dataclass_field(
        default_factory=HeraldicChargeGroup
    )
    tertiary: HeraldicChargeGroup = dataclass_field(default_factory=HeraldicChargeGroup)
    peripheral: HeraldicChargeGroup = dataclass_field(
        default_factory=HeraldicChargeGroup
    )
    peripheral_tertiary: HeraldicChargeGroup = dataclass_field(
        default_factory=HeraldicChargeGroup
    )
    current: str = "primary"
    # Where the *last-added* charge actually landed - usually `current`, but
    # a peripheral redirected out of "primary" (see add_charge) diverges from
    # it, and apply_modifier needs to find that same charge, not whatever
    # group `current` points at next.
    last_group: str = "primary"
    unspecified: list[HeraldicCharge] = dataclass_field(default_factory=list)
    tertiary_after_next: bool = False
    pending_held: HeraldicFeature | None = None

    def current_group(self) -> HeraldicChargeGroup:
        return getattr(self, self.last_group)

    def mark_tertiary_after_next(self) -> None:
        # A new "on" ends any tertiary group still open from an earlier "on
        # X Y" clause in the same blazon ("on a bend... and on a chief...") -
        # X here is a fresh top-level ordinary, not another tertiary of the
        # previous X.
        self.current = "primary"
        self.tertiary_after_next = True

    def enter_secondary(self, relation: HeraldicFeature) -> None:
        self.current = "secondary"
        self.secondary.relation = relation

    def mark_held(self, feat: HeraldicFeature) -> None:
        self.pending_held = feat

    def add_charge(
        self, charge_feats: list[HeraldicFeature], count: HeraldicFeature | None
    ) -> None:
        # A charge that already got its primary tincture is done collecting.
        # Starting a new charge closes that window.
        self.unspecified = [c for c in self.unspecified if c.tincture is None]
        charge_feat = charge_feats[0]
        charged = self.tertiary_after_next
        held = self.pending_held
        self.pending_held = None
        # "maintaining a rose" etc. - a held/maintained/sustained charge is
        # always secondary (my.cat: maintained<held<secondary<second),
        # regardless of whatever `current` was tracking.
        group_name = "secondary" if held else self.current
        if group_name == "primary" and charge_feat.subtype == "peripheral":
            group_name = "peripheral"
        charge = HeraldicCharge(
            charge=charge_feat,
            charge_candidates=charge_feats if len(charge_feats) > 1 else [],
            count=count,
            charged=charged,
            held=held,
        )
        getattr(self, group_name).charges.append(charge)
        self.last_group = group_name
        self.unspecified.append(charge)
        if charged:
            # A tertiary "on" a peripheral is its own grammar step (6), kept
            # apart from tertiaries on (2)/(3) in step (4).
            self.current = (
                "peripheral_tertiary" if group_name == "peripheral" else "tertiary"
            )
            self.tertiary_after_next = False

    def apply_tincture(self, feat: HeraldicFeature) -> None:
        is_secondary = feat.subtype == "tincture2"
        for charge in self.unspecified:
            if is_secondary:
                if charge.tincture is not None and charge.secondary_tincture is None:
                    charge.secondary_tincture = feat
            elif charge.tincture is None:
                charge.tincture = feat
            elif charge.secondary_tincture is None:
                charge.secondary_tincture = feat

    def apply_modifier(self, feat: HeraldicFeature) -> None:
        charges = self.current_group().charges
        if not charges:
            return
        last_charge = charges[-1]
        if feat.feature_type == FeatureType.posture:
            last_charge.posture = feat
        elif feat.feature_type == FeatureType.arrangement:
            last_charge.arrangement = feat
        elif feat.feature_type == FeatureType.charge_treatment:
            last_charge.treatment = feat
        elif feat.feature_type == FeatureType.count:
            last_charge.points = feat
        elif feat.feature_type == FeatureType.line:
            last_charge.line = feat

    def build(
        self,
    ) -> tuple[
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
    ]:
        return (
            self.primary if self.primary.charges else None,
            self.secondary if self.secondary.charges else None,
            self.tertiary if self.tertiary.charges else None,
            self.peripheral if self.peripheral.charges else None,
            self.peripheral_tertiary if self.peripheral_tertiary.charges else None,
        )


def _narrow_by_host_subtype(
    candidates: list[HeraldicFeature],
    host: HeraldicFeature,
    creature_subtypes: list[str],
) -> HeraldicFeature | None:
    """Pick the candidate depending on whether `host` is a creature or not"""
    host_is_creature = host.subtype in creature_subtypes
    matching = [c for c in candidates if bool(c.subtype) == host_is_creature]
    return matching[0] if len(matching) == 1 else None


def _narrow_by_preference(
    candidates: list[HeraldicFeature], preferred_codes: list[str]
) -> HeraldicFeature | None:
    """Pick the candidate with a hand-curated default list."""
    preferred = [c for c in candidates if c.code in preferred_codes]
    return preferred[0] if len(preferred) == 1 else None


def resolve_ambiguous_charges(
    groups: list[HeraldicChargeGroup],
    creature_subtypes: list[str],
    preferred_codes: list[str],
) -> None:
    """Narrow same-span charge candidates - first by the charge next to
    them in the same group, then by a hand-curated default."""
    for group in groups:
        charges = group.charges
        for i, charge in enumerate(charges):
            if not charge.charge_candidates:
                continue
            for host_idx in (i + 1, i - 1):
                if not (0 <= host_idx < len(charges)):
                    continue
                best = _narrow_by_host_subtype(
                    charge.charge_candidates,
                    charges[host_idx].charge,
                    creature_subtypes,
                )
                if best is not None:
                    charge.charge = best
                    charge.charge_candidates = []
                    break
            else:
                if best := _narrow_by_preference(
                    charge.charge_candidates, preferred_codes
                ):
                    charge.charge = best
                    charge.charge_candidates = []


def build_blazon(blazon: str, catalog: FeatureCatalog) -> HeraldicBlazon:
    matches, unmatched = get_blazon_features(blazon, catalog)

    field_features: list[HeraldicFeature] = []
    spans = sorted(matches)
    while spans:
        span = spans[0]
        field_feature = resolve_field_feature(matches[span], field_features)
        if not field_feature:
            break
        matches.pop(span)
        spans.pop(0)
        if (
            field_feature.feature_type == FeatureType.field_treatment
            and field_feature.subtype == "seme"
        ):
            field_feature = complete_seme_feature(field_feature, matches, spans)
        field_features.append(field_feature)
    if not field_features:
        field_features.extend(catalog["fieldless"])
    field: HeraldicField = build_field(field_features)

    charge_features: dict[tuple[int, int], list[HeraldicFeature]] = {
        span: resolve_feature_candidates(candidates)
        for span, candidates in matches.items()
    }
    charge_features.update(
        {
            span: [
                HeraldicFeature(FeatureType.relation, subtype="unknown", details=term)
            ]
            for span, term in unmatched.items()
        }
    )

    charge_group_builder = ChargeGroupBuilder()
    pending_count: HeraldicFeature | None = None
    unknown_terms: list[str] = []

    for span, feat_list in sorted(charge_features.items()):
        feat = feat_list[0]
        if feat.feature_type == FeatureType.relation:
            if feat.details == "on":
                charge_group_builder.mark_tertiary_after_next()
            elif feat.details == "between":
                charge_group_builder.enter_secondary(feat)
            elif feat.details:
                unknown_terms.append(feat.details)
            continue

        if feat.feature_type == FeatureType.count:
            if "count" in feat.codes:
                charge_group_builder.apply_modifier(feat)
            else:
                pending_count = feat
            continue

        if feat.feature_type == FeatureType.group:
            charge_group_builder.mark_held(feat)
            continue

        if feat.feature_type == FeatureType.charge:
            charge_group_builder.add_charge(feat_list, pending_count)
            pending_count = None
            continue

        if feat.feature_type == FeatureType.tincture:
            charge_group_builder.apply_tincture(feat)
            continue

        charge_group_builder.apply_modifier(feat)

    primary, secondary, tertiary, peripheral, peripheral_tertiary = (
        charge_group_builder.build()
    )
    resolve_ambiguous_charges(
        [
            g
            for g in (primary, secondary, tertiary, peripheral, peripheral_tertiary)
            if g
        ],
        catalog.creature_subtypes,
        catalog.preferred_ambiguous_codes,
    )
    return HeraldicBlazon(
        field=field,
        primary=primary,
        secondary=secondary,
        tertiary=tertiary,
        peripheral=peripheral,
        peripheral_tertiary=peripheral_tertiary,
        unknown_terms=unknown_terms,
    )


def parse_blazon(
    blazon: str, catalog: FeatureCatalog, *, include_variants: bool = False
) -> list[str]:
    blazon_struct = build_blazon(blazon, catalog)
    terms = blazon_struct.search_terms(include_variants=include_variants)
    return terms


@dataclass
class TermGroup:
    label: str
    terms: list[str]
    active: bool = True


def grouped_search_terms(
    blazon: HeraldicBlazon, *, include_variants: bool = False
) -> list[TermGroup]:
    """Search terms grouped by the blazon section that produced them.

    `include_variants` controls whether a charge resolved from a variant term
    (e.g. "chicken" -> BIRD) gets an extra variant tag.
    """
    groups = []
    ambiguous_terms: list[str] = []
    if blazon.field:
        groups.append(TermGroup("Field", blazon.field.search_terms()))
    for label, charge_group, group_tag in (
        ("Primary", blazon.primary, "primary"),
        ("Secondary", blazon.secondary, "second"),
        ("Tertiary", blazon.tertiary, "tertiary"),
        ("Peripheral", blazon.peripheral, None),
        ("Peripheral tertiary", blazon.peripheral_tertiary, "tertiary"),
    ):
        if not charge_group:
            continue
        for i, charge in enumerate(charge_group.charges, start=1):
            groups.append(
                TermGroup(
                    f"{label} charge {i}: {charge.charge.subtype}",
                    charge.search_terms(
                        include_variants=include_variants, group_tag=group_tag
                    ),
                )
            )
            # Couldn't narrow to one candidate
            for alt in charge.charge_candidates:
                if alt is charge.charge:
                    continue
                alt_charge = replace(charge, charge=alt, charge_candidates=[])
                ambiguous_terms.extend(
                    alt_charge.search_terms(
                        include_variants=include_variants, group_tag=group_tag
                    )
                )
    if len(groups) == 1 and groups[0].label == "Field":
        groups.append(TermGroup("Uncharged", ["FO"]))
    groups = [g for g in groups if g.terms]
    if ambiguous_terms:
        groups.append(TermGroup("Ambiguous terms", ambiguous_terms, active=False))
    if blazon.unknown_terms:
        groups.append(TermGroup("Unknown terms", blazon.unknown_terms, active=False))
    return groups
