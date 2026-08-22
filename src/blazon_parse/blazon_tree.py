from dataclasses import dataclass, field


@dataclass
class Relation:
    keyword: str
    charges: list[ChargeNode]


@dataclass
class ChargeNode:
    count: str | None = None
    content: str = ""
    tinctures: list[str] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass
class FieldNode:
    fieldless: bool = False
    division: str | None = None
    line: str | None = None
    tinctures: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)


@dataclass
class BlazonTree:
    field: FieldNode
    charge_groups: list[list[ChargeNode]] = field(default_factory=list)
