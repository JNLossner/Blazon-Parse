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
        if cursor.peek() == "and" and match_phrase(
            cursor.words, cursor.pos + 1, tinctures
        ):
            cursor.advance(1)
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


def _match_and_relation(cursor: Cursor) -> tuple[int, str] | None:
    if (
        cursor.peek() != "and"
        or match_quantity(cursor.words, cursor.pos + 1) is not None
    ):
        return None
    m = match_relation(cursor.words, cursor.pos + 1)
    return m if m and not is_fronted_only(m[1]) else None


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
        relations.append(
            Relation(
                keyword=keyword,
                charges=parse_charge_group(
                    cursor, tinctures, allow_and_continuation=False
                ),
            )
        )
    return relations


def parse_charge(
    cursor: Cursor, tinctures: list[str], *, allow_and_continuation: bool = True
) -> ChargeNode:
    if (m := match_relation(cursor.words, cursor.pos, at_start=True)) is not None:
        n, keyword = m
        cursor.advance(n)
        host = parse_charge(cursor, tinctures)
        if cursor.peek() not in (None, ","):
            host.relations.append(
                Relation(
                    keyword=keyword,
                    charges=parse_charge_group(
                        cursor, tinctures, allow_and_continuation=False
                    ),
                )
            )
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
        charge_groups.append(parse_charge_group(cursor, tinctures))

    return BlazonTree(field=field, charge_groups=charge_groups)
