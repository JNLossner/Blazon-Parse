import re

_LOCATIVES = {"on", "between", "within"}
_FRONTED_ONLY = {"on"}
_POSITIONS = {"chief", "base"}
_PREPOSITIONS = {
    "of",
    "with",
    "by",
    "to",
    "from",
    "in",
    "over",
    "on",
    "between",
    "within",
}
_ARTICLES = {"a", "an"}
_NUMBER_WORDS = {
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
}


def lex(blazon: str) -> list[str]:
    normalized = blazon.lower().replace("-", " ")
    return re.findall(r"[a-z']+|,", normalized)


def match_phrase(words: list[str], i: int, phrases: list[str]) -> int | None:
    candidates = sorted(
        (p.lower().replace("-", " ").split() for p in phrases), key=len, reverse=True
    )
    for phrase in candidates:
        n = len(phrase)
        if words[i : i + n] == phrase:
            return n
    return None


def match_relation(
    words: list[str], i: int, *, at_start: bool = False
) -> tuple[int, str] | None:
    if i >= len(words):
        return None
    word = words[i]
    if word in _LOCATIVES:
        return 1, word
    next_word = words[i + 1] if i + 1 < len(words) else None
    if word.endswith("ed") and next_word in _PREPOSITIONS:
        return 2, f"{word} {next_word}"
    if not at_start and word.endswith("ing") and next_word not in (None, ",", "and"):
        return 1, word
    return None


def is_fronted_only(keyword: str) -> bool:
    return keyword in _FRONTED_ONLY


def match_position(words: list[str], i: int) -> tuple[int, str] | None:
    if i >= len(words) or words[i] != "in":
        return None
    next_word = words[i + 1] if i + 1 < len(words) else None
    if next_word in _POSITIONS:
        return 2, next_word
    return None


def match_quantity(words: list[str], i: int) -> int | None:
    if i >= len(words):
        return None
    word = words[i]
    if word in _ARTICLES or word in _NUMBER_WORDS or word.isdigit():
        return 1
    return None
