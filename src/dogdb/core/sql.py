"""Conservative SQL classification using sqlglot's generic dialect."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlglot import ErrorLevel, exp, parse
from sqlglot.optimizer.scope import Scope, ScopeType, traverse_scope


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


_TRANSACTIONS = (exp.Transaction, exp.Commit, exp.Rollback)
_KNOWN_OTHER = (
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Update,
    *_TRANSACTIONS,
)


def _table_name(table: exp.Table) -> str | None:
    parts = [part.name.lower() for part in table.parts if part.name]
    return ".".join(parts) if parts else None


def _within_cte(scope: Scope) -> bool:
    current: Scope | None = scope
    while current is not None:
        if current.scope_type is ScopeType.CTE:
            return True
        current = current.parent
    return False


def _from_tables(query: exp.Select) -> frozenset[str] | None:
    try:
        scopes = traverse_scope(query)
        root = next(scope for scope in scopes if scope.scope_type is ScopeType.ROOT)
        for _, source in root.selected_sources.values():
            if isinstance(source, Scope) and source.scope_type is not ScopeType.CTE:
                return None

        names: set[str] = set()
        for scope in scopes:
            if scope is not root and not _within_cte(scope):
                continue
            for _, source in scope.selected_sources.values():
                if not isinstance(source, exp.Table):
                    continue
                name = _table_name(source)
                if name is None:
                    return None
                names.add(name)
        return frozenset(names) if names else None
    except Exception:
        return None


def _literal_value(query: exp.Select, key: str) -> int | None:
    clause = query.args.get(key)
    if clause is None:
        return None
    literal = clause.expression
    if not isinstance(literal, exp.Literal) or literal.is_string:
        return None
    value = literal.this
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        return None
    return int(value)


def classify_sql(sql: str) -> SQLClassification:
    try:
        expressions = parse(sql, read=None, error_level=ErrorLevel.RAISE)
        if len(expressions) != 1 or expressions[0] is None:
            return SQLClassification(SQLKind.UNKNOWN)
        expression = expressions[0]

        if isinstance(expression, exp.SetOperation):
            return SQLClassification(
                SQLKind.SELECT,
                has_top_level_order_by=expression.args.get("order") is not None,
            )
        if isinstance(expression, exp.Select):
            return SQLClassification(
                SQLKind.SELECT,
                has_top_level_order_by=expression.args.get("order") is not None,
                tables=_from_tables(expression),
                top_level_limit=_literal_value(expression, "limit"),
                top_level_offset=_literal_value(expression, "offset"),
            )
        if isinstance(expression, _KNOWN_OTHER):
            return SQLClassification(
                SQLKind.OTHER,
                is_transaction=isinstance(expression, _TRANSACTIONS),
            )
    except Exception:
        return SQLClassification(SQLKind.UNKNOWN)
    return SQLClassification(SQLKind.UNKNOWN)
