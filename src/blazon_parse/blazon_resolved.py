from dataclasses import dataclass, field

from blazon_parse.heraldic import HeraldicFeature


@dataclass
class ResolvedRelation:
    tag: str
    charged: bool
    charges: list[ResolvedCharge]


@dataclass
class ResolvedCharge:
    content: str
    count: HeraldicFeature | None = None
    features: list[HeraldicFeature] = field(default_factory=list)
    ambiguous: list[HeraldicFeature] = field(default_factory=list)
    tinctures: list[HeraldicFeature] = field(default_factory=list)
    relations: list[ResolvedRelation] = field(default_factory=list)


@dataclass
class ResolvedField:
    content: str = ""
    features: list[HeraldicFeature] = field(default_factory=list)
    tinctures: list[HeraldicFeature] = field(default_factory=list)


@dataclass
class ResolvedBlazon:
    field: ResolvedField
    charge_groups: list[list[ResolvedCharge]] = field(default_factory=list)
