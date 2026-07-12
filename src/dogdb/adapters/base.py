"""Shared adapter helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from dogdb.core.models import LogicalResult


class Adapter(Protocol):
    """Backend contract consumed by the connection proxy."""

    sql_capable_attrs: frozenset[str] = frozenset()

    def execute(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> LogicalResult: ...

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> LogicalResult: ...

    def close(self) -> None: ...

    @property
    def in_transaction(self) -> bool: ...


def materialize(cursor: Any) -> LogicalResult:
    description = cursor.description
    if description is None:
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))
    columns = [str(column[0]) for column in description]
    column_types = [column[1] for column in description]
    rows = [tuple(row) for row in cursor.fetchall()]
    return LogicalResult(columns, rows, len(rows), column_types)
