from dataclasses import dataclass
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

    for key, value in FEATURE_TYPE_MAP.items():
        if key in category:
            return value

    return FeatureType.charge


@dataclass
class HeraldicFeature:
    feature_type: FeatureType
    subtype: str
    code: str
    details: str | None = None
