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


def _tokens(sql: str) -> list[tuple[str, int]] | None:
    tokens: list[tuple[str, int]] = []
    word: list[str] = []
    depth = 0
    quote: str | None = None
    index = 0

    def flush() -> None:
        if word:
            tokens.append(("".join(word).lower(), depth))
            word.clear()

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote is not None:
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                quote = None
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
            depth += 1
        elif char == ")":
            flush()
            depth -= 1
            if depth < 0:
                return None
        elif char == ";":
            flush()
            if sql[index + 1 :].strip():
                return None
        elif char.isalnum() or char == "_":
            word.append(char)
        else:
            flush()
        index += 1
    flush()
    return tokens if quote is None and depth == 0 else None


def classify_sql(sql: str) -> SQLClassification:
    tokens = _tokens(sql)
    if not tokens:
        return SQLClassification(SQLKind.UNKNOWN)
    top_level = [token for token, depth in tokens if depth == 0]
    if not top_level:
        return SQLClassification(SQLKind.UNKNOWN)
    if top_level[0] == "select":
        ordered = any(
            top_level[index : index + 2] == ["order", "by"]
            for index in range(len(top_level) - 1)
        )
        return SQLClassification(SQLKind.SELECT, ordered)
    if top_level[0] in _KNOWN_OTHER:
        return SQLClassification(
            SQLKind.OTHER,
            is_transaction=top_level[0] in {"begin", "commit", "rollback"},
        )
    return SQLClassification(SQLKind.UNKNOWN)
