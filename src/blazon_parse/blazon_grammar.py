from dataclasses import dataclass

from blazon_parse.blazon_terminals import (
    is_fronted_only,
    lex,
    match_phrase,
    match_quantity,
    match_relation,
)
from blazon_parse.blazon_tree import BlazonTree, ChargeNode, FieldNode, Relation


@dataclass
class Cursor:
    words: list[str]
    pos: int = 0

    def peek(self) -> str | None:
        return self.words[self.pos] if self.pos < len(self.words) else None

    def advance(self, n: int = 1) -> None:
        self.pos += n


def parse_tincture_list(cursor: Cursor, tinctures: list[str]) -> list[str]:
    result = []
    while (n := match_phrase(cursor.words, cursor.pos, tinctures)) is not None:
        result.append(" ".join(cursor.words[cursor.pos : cursor.pos + n]))
        cursor.advance(n)
        skip = 1 if cursor.peek() == "," else 0
        if cursor.words[cursor.pos + skip : cursor.pos + skip + 1] == ["and"]:
            skip += 1
        if skip and match_phrase(cursor.words, cursor.pos + skip, tinctures):
            cursor.advance(skip)
        else:
            break
    return result


def parse_content(cursor: Cursor, tinctures: list[str]) -> str:
    start = cursor.pos
    while cursor.peek() not in (None, ",", "and"):
        if match_phrase(cursor.words, cursor.pos, tinctures) is not None:
            break
        if (
            match_relation(cursor.words, cursor.pos, at_start=cursor.pos == start)
            is not None
        ):
            break
        cursor.advance(1)
    return " ".join(cursor.words[start : cursor.pos])


def _is_new_charge_signal(words: list[str], pos: int) -> bool:
    """A quantity, or a relation word that always re-states its own host
    (e.g. "on"), both mean an independent charge starts here."""
    if match_quantity(words, pos) is not None:
        return True
    m = match_relation(words, pos, at_start=True)
    return m is not None and is_fronted_only(m[1])


def _match_and_relation(cursor: Cursor) -> tuple[int, str] | None:
    if cursor.peek() != "and" or _is_new_charge_signal(cursor.words, cursor.pos + 1):
        return None
    return match_relation(cursor.words, cursor.pos + 1)


def _deepest_charge(charge: ChargeNode) -> ChargeNode:
    while charge.relations:
        charge = charge.relations[-1].charges[-1]
    return charge


def _parse_relation(cursor: Cursor, keyword: str, tinctures: list[str]) -> Relation:
    return Relation(
        keyword=keyword,
        charges=parse_charge_group(cursor, tinctures, allow_and_continuation=False),
    )


def _extend_previous_charge(
    cursor: Cursor, charge: ChargeNode, tinctures: list[str]
) -> None:
    start = cursor.pos
    while cursor.peek() not in (None, ","):
        if match_phrase(cursor.words, cursor.pos, tinctures) is not None:
            break
        if match_relation(cursor.words, cursor.pos) is not None:
            break
        if cursor.peek() == "and" and (
            match_quantity(cursor.words, cursor.pos + 1) is not None
            or match_relation(cursor.words, cursor.pos + 1) is not None
        ):
            break
        cursor.advance(1)
    extra = " ".join(cursor.words[start : cursor.pos])
    charge.content = f"{charge.content} {extra}".strip()
    charge.tinctures.extend(parse_tincture_list(cursor, tinctures))
    charge.relations.extend(parse_relations(cursor, tinctures))


def parse_relations(
    cursor: Cursor, tinctures: list[str], *, allow_and_continuation: bool = True
) -> list[Relation]:
    relations = []
    while True:
        if (m := match_relation(cursor.words, cursor.pos)) is not None:
            n, keyword = m
        elif allow_and_continuation and (m := _match_and_relation(cursor)) is not None:
            cursor.advance(1)
            n, keyword = m
        else:
            break
        cursor.advance(n)
        relations.append(_parse_relation(cursor, keyword, tinctures))
    return relations


def parse_charge(
    cursor: Cursor, tinctures: list[str], *, allow_and_continuation: bool = True
) -> ChargeNode:
    if cursor.peek() == "and":
        cursor.advance(1)

    if (m := match_relation(cursor.words, cursor.pos, at_start=True)) is not None:
        n, keyword = m
        cursor.advance(n)
        host = parse_charge(cursor, tinctures)
        skip = 1 if cursor.peek() == "," else 0
        if cursor.words[cursor.pos + skip : cursor.pos + skip + 1]:
            cursor.advance(skip)
            host.relations.append(_parse_relation(cursor, keyword, tinctures))
        else:
            host.content = f"{keyword} {host.content}".strip()
        return host

    count = None
    if match_quantity(cursor.words, cursor.pos) is not None:
        count = cursor.words[cursor.pos]
        cursor.advance(1)
    content = parse_content(cursor, tinctures)
    charge_tinctures = parse_tincture_list(cursor, tinctures)
    relations = parse_relations(
        cursor, tinctures, allow_and_continuation=allow_and_continuation
    )
    return ChargeNode(
        count=count, content=content, tinctures=charge_tinctures, relations=relations
    )


def parse_charge_group(
    cursor: Cursor, tinctures: list[str], *, allow_and_continuation: bool = True
) -> list[ChargeNode]:
    charges = [
        parse_charge(cursor, tinctures, allow_and_continuation=allow_and_continuation)
    ]
    while cursor.peek() == "and" and _match_and_relation(cursor) is None:
        cursor.advance(1)
        charges.append(
            parse_charge(
                cursor, tinctures, allow_and_continuation=allow_and_continuation
            )
        )
    return charges


def parse_field(
    cursor: Cursor, tinctures: list[str], divisions: list[str], treatments: list[str]
) -> FieldNode:
    division = None
    n = match_phrase(cursor.words, cursor.pos, divisions)
    n = n if n is not None else match_phrase(cursor.words, cursor.pos, treatments)
    if n is not None:
        division = " ".join(cursor.words[cursor.pos : cursor.pos + n])
        cursor.advance(n)

    field_tinctures = parse_tincture_list(cursor, tinctures)

    modifier_start = cursor.pos
    while cursor.peek() not in (None, ","):
        cursor.advance(1)
    modifiers = (
        [" ".join(cursor.words[modifier_start : cursor.pos])]
        if cursor.pos > modifier_start
        else []
    )

    return FieldNode(division=division, tinctures=field_tinctures, modifiers=modifiers)


def parse_blazon(
    blazon: str,
    *,
    tinctures: list[str],
    divisions: list[str],
    treatments: list[str],
) -> BlazonTree:
    cursor = Cursor(lex(blazon))

    if cursor.peek() == "fieldless":
        cursor.advance(1)
        if cursor.peek() == ",":
            cursor.advance(1)
        field = FieldNode(fieldless=True)
    else:
        field = parse_field(cursor, tinctures, divisions, treatments)

    charge_groups = []
    if cursor.peek() not in (None, ","):
        charge_groups.append(parse_charge_group(cursor, tinctures))
    while cursor.peek() == ",":
        cursor.advance(1)
        if cursor.peek() is None:
            break
        if cursor.peek() == "and" and charge_groups:
            m = _match_and_relation(cursor)
            if m is None:
                cursor.advance(1)
                charge_groups[-1].append(parse_charge(cursor, tinctures))
            else:
                n, keyword = m
                cursor.advance(1 + n)
                _deepest_charge(charge_groups[-1][-1]).relations.append(
                    _parse_relation(cursor, keyword, tinctures)
                )
        elif charge_groups and not _is_new_charge_signal(cursor.words, cursor.pos):
            _extend_previous_charge(
                cursor, _deepest_charge(charge_groups[-1][-1]), tinctures
            )
        else:
            charge_groups.append(parse_charge_group(cursor, tinctures))

    return BlazonTree(field=field, charge_groups=charge_groups)
