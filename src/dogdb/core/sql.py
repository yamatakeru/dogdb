"""SQL classification backed by sqlglot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


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
    top_level_limit: int | None = None
    top_level_offset: int | None = None


_OTHER_COMMANDS = frozenset({
    exp.Insert, exp.Update, exp.Delete, exp.Create,
    exp.Drop, exp.TruncateTable, exp.Alter, exp.Merge,
})

_TRANSACTION_COMMANDS = frozenset({
    exp.Transaction, exp.Commit, exp.Rollback,
})


def classify_sql(sql: str) -> SQLClassification:
    try:
        tree = sqlglot.parse_one(sql)
    except ParseError:
        return SQLClassification(SQLKind.UNKNOWN)

    if isinstance(tree, exp.Query):
        order = tree.args.get("order")
        has_order_by = order is not None and len(order.expressions) > 0
        return SQLClassification(
            SQLKind.SELECT,
            has_top_level_order_by=has_order_by,
            tables=_extract_tables(tree),
            top_level_limit=_extract_limit(tree),
            top_level_offset=_extract_offset(tree),
        )

    if isinstance(tree, tuple(_TRANSACTION_COMMANDS)):
        return SQLClassification(SQLKind.OTHER, is_transaction=True)

    if isinstance(tree, tuple(_OTHER_COMMANDS)):
        return SQLClassification(SQLKind.OTHER)

    return SQLClassification(SQLKind.UNKNOWN)


def _extract_tables(tree: exp.Query) -> frozenset[str] | None:
    tables: set[str] = set()
    for node in tree.find_all(exp.Table):
        name = node.name.lower()
        if node.db:
            name = f"{node.db.lower()}.{name}"
        tables.add(name)
    return frozenset(tables) if tables else None


def _extract_limit(tree: exp.Query) -> int | None:
    limit = tree.args.get("limit")
    if limit is None:
        return None
    expr = limit.args.get("expression")
    if expr is None or not isinstance(expr, exp.Literal):
        return None
    try:
        return int(expr.name)
    except (ValueError, AttributeError):
        return None


def _extract_offset(tree: exp.Query) -> int | None:
    offset = tree.args.get("offset")
    if offset is None:
        return None
    expr = offset.args.get("expression")
    if expr is None or not isinstance(expr, exp.Literal):
        return None
    try:
        return int(expr.name)
    except (ValueError, AttributeError):
        return None
