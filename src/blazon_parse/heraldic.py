from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum, auto


class FeatureType(StrEnum):
    charge = auto()
    charge_treatment = auto()
    posture = auto()
    field = auto()
    field_division = auto()
    field_treatment = auto()
    tincture = auto()
    count = auto()
    arrangement = auto()
    relation = auto()


FEATURE_TYPE_MAP: dict[str, FeatureType] = {
    " ".join(feat.name.split("_")): feat for feat in FeatureType
}


def to_feature_type(category: str) -> FeatureType:
    if category in FEATURE_TYPE_MAP:
        return FEATURE_TYPE_MAP[category]

    for key, value in sorted(FEATURE_TYPE_MAP.items(), reverse=True):
        if key in category:
            return value

    return FeatureType.charge


@dataclass
class HeraldicFeature:
    feature_type: FeatureType
    subtype: str
    code: str = ""
    details: str | None = None

    def search_term(self) -> str | None:
        """The literal string an O&A complex search would match on.

        Catalog categories (charges, field patterns, ordinaries...) carry a
        translated `code` (e.g. "CAT", "AR"); features with no catalog code
        (bare tinctures, postures, relations) search on the matched text
        itself.
        """
        return self.code or self.details


def _tags(*features: HeraldicFeature | None) -> list[str]:
    return [term for f in features if f is not None and (term := f.search_term())]


def _tincture_tags(
    tincture: HeraldicFeature | None, secondary: HeraldicFeature | None
) -> list[str]:
    """Tincture tags, stripping the "~" parti-tincture marker when there's no pair."""
    tags = _tags(tincture)
    if tags and secondary is None:
        tags = [tags[0].removeprefix("~").strip()]
    tags.extend(_tags(secondary))
    return tags


def _line(code: str, tags: list[str]) -> str:
    return ":".join([code, *tags])


@dataclass
class HeraldicField:
    tincture: HeraldicFeature
    division: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None

    def search_terms(self) -> list[str]:
        tincture_tags = _tincture_tags(self.tincture, self.secondary_tincture)
        division_tags = _tags(self.division) or ["solid"]

        if self.treatment is not None and self.treatment.code:
            lines = [_line("FIELD", [*division_tags, *tincture_tags])]
            lines.append(_line(self.treatment.search_term(), tincture_tags))
        else:
            lines = [
                _line("FIELD", [*division_tags, *tincture_tags, *_tags(self.treatment)])
            ]

        return lines


@dataclass
class HeraldicCharge:
    charge: HeraldicFeature
    count: HeraldicFeature | None = None
    tincture: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    posture: HeraldicFeature | None = None
    arrangement: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None

    def search_terms(self) -> list[str]:
        code = self.charge.search_term()
        if not code:
            return []

        # Attributes with their own catalog code (e.g. "demi" -> BEAST9DEMI)
        # become their own line, carrying only count/tincture
        shared_tags = [
            *_tags(self.count),
            *_tincture_tags(self.tincture, self.secondary_tincture),
        ]
        modifiers = [self.posture, self.arrangement, self.treatment]
        coded_modifiers = [m for m in modifiers if m is not None and m.code]
        plain_modifiers = [m for m in modifiers if m is not None and not m.code]

        lines = [_line(code, [*shared_tags, *_tags(*plain_modifiers)])]
        lines.extend(_line(m.search_term(), shared_tags) for m in coded_modifiers)
        return lines


@dataclass
class HeraldicChargeGroup:
    """One or more charges that share a position in the blazon."""

    charges: list[HeraldicCharge] = dataclass_field(default_factory=list)
    relation: HeraldicFeature | None = None

    def search_terms(self) -> list[str]:
        return [line for charge in self.charges for line in charge.search_terms()]


@dataclass
class HeraldicBlazon:
    field: HeraldicField | None
    primary: HeraldicChargeGroup | None = None
    secondary: HeraldicChargeGroup | None = None
    tertiary: HeraldicChargeGroup | None = None

    def search_terms(self) -> list[str]:
        terms = self.field.search_terms() if self.field else ["NO"]
        for group in (self.primary, self.secondary, self.tertiary):
            if group:
                terms.extend(group.search_terms())
        return terms
