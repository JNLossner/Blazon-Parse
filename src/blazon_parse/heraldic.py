from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum, auto


class FeatureType(StrEnum):
    charge = auto()
    charge_treatment = auto()
    posture = auto()
    field_division = auto()
    field_treatment = auto()
    tincture = auto()
    count = auto()
    arrangement = auto()
    relation = auto()
    line = auto()
    group = auto()


FEATURE_TYPE_MAP: dict[str, FeatureType] = {
    " ".join(feat.name.split("_")): feat for feat in FeatureType
}


def to_feature_type(category: str) -> FeatureType:
    if category in FEATURE_TYPE_MAP:
        return FEATURE_TYPE_MAP[category]

    for key, value in sorted(FEATURE_TYPE_MAP.items(), reverse=True):
        if key in category:
            return value

    if category == "number":
        return FeatureType.count

    if category in ("field", "fieldless"):
        return FeatureType.field_division

    if "orientation" in category:
        return FeatureType.posture
    if "_dir" in category:
        return FeatureType.posture

    if category in ("tertiaries", "style"):
        return FeatureType.charge_treatment
    if "type" in category:
        return FeatureType.charge_treatment
    if "family" in category:
        return FeatureType.charge_treatment

    return FeatureType.charge


@dataclass
class HeraldicFeature:
    feature_type: FeatureType
    subtype: str
    codes: dict[str, str] = dataclass_field(default_factory=dict)
    details: str | None = None

    @property
    def code(self) -> str:
        """This feature's own code, or an arbitrary one if it's scope-ambiguous.

        Some catalog terms (e.g. "demi") carry a different code per governing
        scope ("beast" vs "bird" vs "monster"...), stored in `codes` keyed by
        that scope. Reading `.code` without knowing the real scope just picks
        one; callers that know the scope should use `search_term(scope=...)`.
        """
        return self.codes.get(self.subtype) or next(iter(self.codes.values()), "")

    def search_term(self, scope: str | None = None) -> str | None:
        """The literal string an O&A complex search would match on.

        Catalog categories (charges, field patterns, ordinaries...) carry a
        translated code (e.g. "CAT", "AR"); features with no catalog code
        (bare tinctures, postures, relations) search on the matched text
        itself.
        """
        if scope is not None and scope in self.codes:
            return self.codes[scope]
        return self.code or self.details


def _tags(*features: HeraldicFeature | None) -> list[str]:
    return [term for f in features if f is not None and (term := f.search_term())]


def _tincture_tags(
    tincture: HeraldicFeature | None, secondary: HeraldicFeature | None
) -> list[str]:
    """Tincture tags, stripping the "~" parti-tincture marker when there's no pair."""
    secondary_term = secondary.search_term(scope="tincture2") if secondary else None
    primary_term = (
        tincture.search_term(scope=("tincture1" if secondary_term else "tincture"))
        if tincture
        else None
    )

    return [term for term in (primary_term, secondary_term) if term]


def _line(code: str, tags: list[str]) -> str:
    return ":".join([code, *tags])


@dataclass
class HeraldicField:
    tincture: HeraldicFeature
    division: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None

    def search_terms(self) -> list[str]:
        # A specifically-coded line (PB, a FIELD TREATMENT-... code) drops
        # the primary's "~" pairing marker - only the generic "FIELD:" line
        # (whether "solid" or a "divided X" synonym) keeps both tilded, the
        # same as a charge's tincture pair.
        tincture_tags = _tincture_tags(
            self.tincture or self.treatment, self.secondary_tincture
        )
        bare_primary_tags = [t.removeprefix("~ ") for t in tincture_tags]

        division_coded = self.division and self.division.code
        treatment_coded = self.treatment and self.treatment.code
        is_seme = self.treatment and self.treatment.subtype == "seme"

        lines = []

        # A coded division or treatment carries the tincture - except a
        # "semy of X" treatment, which describes an added charge, not the
        # field's own tincture, so the base FIELD line still stands beside it.
        if not division_coded and (not treatment_coded or is_seme) and self.tincture:
            lines.append(self.tincture.search_term(scope="field"))
            lines.append(self.tincture.search_term(scope="FIELD"))

        if division_coded:
            lines.append(_line(self.division.search_term(), bare_primary_tags))
            if "divided" in self.division.codes:
                lines.append(
                    _line("FIELD", [self.division.codes["divided"], *tincture_tags])
                )

        if not treatment_coded:
            return lines

        if not is_seme:
            lines.append(_line(self.treatment.search_term(), bare_primary_tags))
            if "FIELD" in self.treatment.codes:
                lines.append(self.treatment.search_term(scope="FIELD"))
        else:
            # A "semy of X" pattern names a charge strewn across the whole
            # field - its tincture is independent of the field's own
            seme_tag = self.treatment.codes.get("tincture")
            seme_tags = [seme_tag] if seme_tag else []
            if charge_code := self.treatment.codes.get("charge"):
                lines.append(_line(charge_code, [*seme_tags, "seme", "seme on field"]))
            lines.append(_line(self.treatment.search_term(), seme_tags))

        return lines


@dataclass
class HeraldicCharge:
    charge: HeraldicFeature
    count: HeraldicFeature | None = None
    points: HeraldicFeature | None = None
    tincture: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    posture: HeraldicFeature | None = None
    arrangement: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None

    def search_terms(self, *, include_variants: bool = False) -> list[str]:
        code = self.charge.search_term()
        if not code:
            return []

        # Attributes with their own catalog code (e.g. "demi" -> BEAST9DEMI)
        # become their own line, carrying only count/points/tincture
        shared_tags = [
            *_tags(self.count, self.points),
            *_tincture_tags(self.tincture or self.treatment, self.secondary_tincture),
        ]
        modifiers = [self.arrangement, self.treatment]
        coded_modifiers = [m for m in modifiers if m is not None and m.code]
        plain_modifiers = [m for m in modifiers if m is not None and not m.code]

        charge_tags = [*shared_tags, *_tags(self.posture, *plain_modifiers)]

        # A charge resolved from a variant term (e.g. "chicken" -> BIRD)
        # carries that variant in `details` alongside its own code.
        if include_variants and self.charge.code and self.charge.details:
            lines = [_line(code, [*charge_tags, self.charge.details])]
        else:
            lines = [_line(code, charge_tags)]

        lines.extend(_line(m.search_term(), shared_tags) for m in coded_modifiers)
        return lines


@dataclass
class HeraldicChargeGroup:
    """One or more charges that share a position in the blazon."""

    charges: list[HeraldicCharge] = dataclass_field(default_factory=list)
    relation: HeraldicFeature | None = None

    def search_terms(self, *, include_variants: bool = False) -> list[str]:
        return [
            line
            for charge in self.charges
            for line in charge.search_terms(include_variants=include_variants)
        ]


@dataclass
class HeraldicBlazon:
    field: HeraldicField | None
    primary: HeraldicChargeGroup | None = None
    secondary: HeraldicChargeGroup | None = None
    tertiary: HeraldicChargeGroup | None = None

    def search_terms(self, *, include_variants: bool = False) -> list[str]:
        terms = self.field.search_terms() if self.field else []
        charges = (self.primary, self.secondary, self.tertiary)
        if not any(c for c in charges):
            terms.append("FO")
        for group in charges:
            if group:
                terms.extend(group.search_terms(include_variants=include_variants))
        return terms
