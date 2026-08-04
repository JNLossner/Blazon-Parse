from dataclasses import dataclass
from dataclasses import field as dataclass_field

from blazon_parse.catalog_parser import ParsedCatalog
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
    blazon: str, catalog: ParsedCatalog
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
    if coded := [c for c in candidates if c.code]:
        candidates = coded
    if tincture1 := [c for c in candidates if c.subtype == "tincture1"]:
        candidates = tincture1

    return None if not candidates else candidates[0]


def resolve_field_feature(
    candidates: list[HeraldicFeature], field_features: list[HeraldicFeature]
) -> HeraldicFeature | None:
    if not field_features:
        candidates = [c for c in candidates if "field" in c.feature_type]
    else:
        candidates = [
            c
            for c in candidates
            if c.feature_type in (FeatureType.field_treatment, FeatureType.tincture)
        ]

    return resolve_feature(candidates)


def build_field(field_features: list[HeraldicFeature]):
    tincture: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    division: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None

    for feat in field_features:
        if feat.feature_type == FeatureType.field_division:
            division = feat
        elif feat.feature_type == FeatureType.field_treatment:
            treatment = feat
        elif tincture is None:
            tincture = feat
        else:
            secondary_tincture = feat

    return HeraldicField(
        tincture=tincture or HeraldicFeature(FeatureType.field, "unknown"),
        division=division,
        secondary_tincture=secondary_tincture,
        treatment=treatment,
    )


@dataclass
class ChargeGroupBuilder:
    primary: HeraldicChargeGroup = dataclass_field(default_factory=HeraldicChargeGroup)
    secondary: HeraldicChargeGroup = dataclass_field(
        default_factory=HeraldicChargeGroup
    )
    tertiary: HeraldicChargeGroup = dataclass_field(default_factory=HeraldicChargeGroup)
    current: str = "primary"
    unspecified: list[HeraldicCharge] = dataclass_field(default_factory=list)
    tertiary_after_next: bool = False

    def current_group(self) -> HeraldicChargeGroup:
        return getattr(self, self.current)

    def mark_tertiary_after_next(self) -> None:
        self.tertiary_after_next = True

    def enter_secondary(self, relation: HeraldicFeature) -> None:
        self.current = "secondary"
        self.secondary.relation = relation

    def add_charge(
        self, charge_feat: HeraldicFeature, count: HeraldicFeature | None
    ) -> None:
        # A charge that already got its primary tincture is done collecting.
        # Starting a new charge closes that window.
        self.unspecified = [c for c in self.unspecified if c.tincture is None]
        charge = HeraldicCharge(charge=charge_feat, count=count)
        self.current_group().charges.append(charge)
        self.unspecified.append(charge)
        if self.tertiary_after_next:
            self.current = "tertiary"
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

    def build(
        self,
    ) -> tuple[
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
        HeraldicChargeGroup | None,
    ]:
        return (
            self.primary if self.primary.charges else None,
            self.secondary if self.secondary.charges else None,
            self.tertiary if self.tertiary.charges else None,
        )


def build_blazon(blazon: str, catalog: ParsedCatalog) -> HeraldicBlazon:
    matches, unmatched = get_blazon_features(blazon, catalog)

    field: HeraldicField | None = None
    if "fieldless" not in blazon.lower():
        field_features: list[HeraldicFeature] = []
        for span, candidates in sorted(matches.items()):
            if field_feature := resolve_field_feature(candidates, field_features):
                field_features.append(field_feature)
                matches.pop(span)
            else:
                break
        field = build_field(field_features)

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
            pending_count = feat
            continue

        if feat.feature_type == FeatureType.charge:
            charge_group_builder.add_charge(feat, pending_count)
            pending_count = None
            continue

        if feat.feature_type == FeatureType.tincture:
            charge_group_builder.apply_tincture(feat)
            continue

        charge_group_builder.apply_modifier(feat)

    primary, secondary, tertiary = charge_group_builder.build()
    return HeraldicBlazon(
        field=field,
        primary=primary,
        secondary=secondary,
        tertiary=tertiary,
    )


def parse_blazon(blazon: str, catalog: ParsedCatalog):
    blazon_struct = build_blazon(blazon, catalog)
    print(blazon)
    print(blazon_struct)
