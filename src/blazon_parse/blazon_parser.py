from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field

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


def get_blazon_features(
    blazon: str, catalog: FeatureCatalog
) -> tuple[
    dict[tuple[int, int], list[HeraldicFeature]],
    dict[tuple[int, int], str],
]:
    matches = find_catalog_matches(blazon.lower(), catalog)

    cleaned_blazon = blazon.replace(",", " ").replace(".", " ")
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

    return matches, unmatched_features


def resolve_feature(candidates: list[HeraldicFeature]) -> HeraldicFeature | None:
    """Pick the candidate feature for a matched span, folding in a same-span variant tag."""
    if not candidates:
        return None

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
            primary = replace(primary, details=variant.search_term())

    return primary


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
        self, charge_feat: HeraldicFeature, count: HeraldicFeature | None
    ) -> None:
        # A charge that already got its primary tincture is done collecting.
        # Starting a new charge closes that window.
        self.unspecified = [c for c in self.unspecified if c.tincture is None]
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
            charge=charge_feat, count=count, charged=charged, held=held
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

    charge_features: dict[tuple[int, int], HeraldicFeature] = {
        span: resolve_feature(candidates) for span, candidates in matches.items()
    }
    charge_features.update(
        {
            span: HeraldicFeature(FeatureType.relation, subtype="unknown", details=term)
            for span, term in unmatched.items()
        }
    )

    charge_group_builder = ChargeGroupBuilder()
    pending_count: HeraldicFeature | None = None

    for span, feat in sorted(charge_features.items()):
        if feat.feature_type == FeatureType.relation:
            if feat.details == "on":
                charge_group_builder.mark_tertiary_after_next()
            if feat.details == "between":
                charge_group_builder.enter_secondary(feat)
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
            charge_group_builder.add_charge(feat, pending_count)
            pending_count = None
            continue

        if feat.feature_type == FeatureType.tincture:
            charge_group_builder.apply_tincture(feat)
            continue

        charge_group_builder.apply_modifier(feat)

    primary, secondary, tertiary, peripheral, peripheral_tertiary = (
        charge_group_builder.build()
    )
    return HeraldicBlazon(
        field=field,
        primary=primary,
        secondary=secondary,
        tertiary=tertiary,
        peripheral=peripheral,
        peripheral_tertiary=peripheral_tertiary,
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


def grouped_search_terms(
    blazon: HeraldicBlazon, *, include_variants: bool = False
) -> list[TermGroup]:
    """Search terms grouped by the blazon section that produced them.

    `include_variants` controls whether a charge resolved from a variant term
    (e.g. "chicken" -> BIRD) gets an extra variant tag.
    """
    groups = []
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
    if len(groups) == 1 and groups[0].label == "Field":
        groups.append(TermGroup("Uncharged", ["FO"]))
    return [g for g in groups if g.terms]
