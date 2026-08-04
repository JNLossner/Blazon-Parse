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


@dataclass
class HeraldicField:
    tincture: HeraldicFeature
    division: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None


@dataclass
class HeraldicCharge:
    charge: HeraldicFeature
    count: HeraldicFeature | None = None
    tincture: HeraldicFeature | None = None
    secondary_tincture: HeraldicFeature | None = None
    posture: HeraldicFeature | None = None
    arrangement: HeraldicFeature | None = None
    treatment: HeraldicFeature | None = None


@dataclass
class HeraldicChargeGroup:
    charges: list[HeraldicCharge] = dataclass_field(default_factory=list)
    relation: HeraldicFeature | None = None


@dataclass
class HeraldicBlazon:
    field: HeraldicField
    primary: HeraldicChargeGroup | None = None
    secondary: HeraldicChargeGroup | None = None
    tertiary: HeraldicChargeGroup | None = None
