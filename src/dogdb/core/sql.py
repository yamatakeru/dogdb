"""Conservative SQL classification without a parser dependency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SQLKind(Enum):
    SELECT = "select"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SQLClassification:
    kind: SQLKind
    has_top_level_order_by: bool | None = None
    is_transaction: bool = False
    tables: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class _Token:
    value: str
    depth: int
    kind: str = "word"


_KNOWN_OTHER = {
    "begin",
    "commit",
    "create",
    "delete",
    "drop",
    "insert",
    "rollback",
    "update",
}


def _tokens(sql: str) -> list[_Token] | None:
    tokens: list[_Token] = []
    word: list[str] = []
    depth = 0
    quote: str | None = None
    quoted_identifier: list[str] = []
    index = 0

    def flush() -> None:
        if word:
            tokens.append(_Token("".join(word).lower(), depth))
            word.clear()

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote is not None:
            if char == quote:
                if next_char == quote:
                    if quote == '"':
                        quoted_identifier.append(char)
                    index += 2
                    continue
                if quote == '"':
                    tokens.append(
                        _Token("".join(quoted_identifier).lower(), depth, "identifier")
                    )
                    quoted_identifier.clear()
                quote = None
            elif quote == '"':
                quoted_identifier.append(char)
            index += 1
            continue
        if char in ("'", '"'):
            flush()
            quote = char
        elif char == "-" and next_char == "-":
            flush()
            index = sql.find("\n", index + 2)
            if index < 0:
                break
            continue
        elif char == "/" and next_char == "*":
            flush()
            end = sql.find("*/", index + 2)
            if end < 0:
                return None
            index = end + 2
            continue
        elif char == "(":
            flush()
            tokens.append(_Token(char, depth, "symbol"))
            depth += 1
        elif char == ")":
            flush()
            depth -= 1
            if depth < 0:
                return None
            tokens.append(_Token(char, depth, "symbol"))
        elif char == ";":
            flush()
            if sql[index + 1 :].strip():
                return None
        elif char.isalnum() or char == "_":
            word.append(char)
        else:
            flush()
            if char in {".", ","}:
                tokens.append(_Token(char, depth, "symbol"))
        index += 1
    flush()
    return tokens if quote is None and depth == 0 else None


def _from_tables(tokens: list[_Token]) -> frozenset[str] | None:
    top_level = [token for token in tokens if token.depth == 0]
    tables: set[str] = set()
    for index, token in enumerate(top_level):
        if token.kind != "word" or token.value not in {"from", "join"}:
            continue
        if index + 1 >= len(top_level):
            return None
        first = top_level[index + 1]
        if first.kind not in {"word", "identifier"}:
            return None
        name = first.value
        if index + 3 < len(top_level) and top_level[index + 2].value == ".":
            second = top_level[index + 3]
            if second.kind not in {"word", "identifier"}:
                return None
            name = f"{name}.{second.value}"
        following = top_level[index + 2] if index + 2 < len(top_level) else None
        if following is not None and following.value == "(":
            return None
        tables.add(name)
    return frozenset(tables) if tables else None


def classify_sql(sql: str) -> SQLClassification:
    tokens = _tokens(sql)
    if not tokens:
        return SQLClassification(SQLKind.UNKNOWN)
    top_level = [token.value for token in tokens if token.depth == 0]
    if not top_level:
        return SQLClassification(SQLKind.UNKNOWN)
    if top_level[0] == "select":
        ordered = any(
            top_level[index : index + 2] == ["order", "by"]
            for index in range(len(top_level) - 1)
        )
        return SQLClassification(SQLKind.SELECT, ordered, tables=_from_tables(tokens))
    if top_level[0] in _KNOWN_OTHER:
        return SQLClassification(
            SQLKind.OTHER,
            is_transaction=top_level[0] in {"begin", "commit", "rollback"},
        )
    return SQLClassification(SQLKind.UNKNOWN)
