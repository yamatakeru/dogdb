"""Shared adapter helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from dogdb.core.models import LogicalResult


_FETCH_CHUNK_SIZE = 1_000


class RowCapExceeded(Exception):
    """Internal signal raised when an adapter observes row_cap + 1 rows."""


class Adapter(Protocol):
    """Backend contract consumed by the connection proxy."""

    sql_capable_attrs: frozenset[str] = frozenset()

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        row_cap: int | None = None,
    ) -> LogicalResult: ...

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> LogicalResult: ...

    def close(self) -> None: ...

    @property
    def in_transaction(self) -> bool: ...


def materialize(cursor: Any, *, row_cap: int | None = None) -> LogicalResult:
    description = cursor.description
    if description is None:
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))
    columns = [str(column[0]) for column in description]
    column_types = [column[1] for column in description]
    if row_cap is None:
        rows = [tuple(row) for row in cursor.fetchall()]
        return LogicalResult(columns, rows, len(rows), column_types)
    rows = []
    while len(rows) <= row_cap:
        amount = min(_FETCH_CHUNK_SIZE, row_cap + 1 - len(rows))
        batch = cursor.fetchmany(amount)
        rows.extend(tuple(row) for row in batch)
        if len(rows) > row_cap:
            raise RowCapExceeded
        if not batch:
            break
    return LogicalResult(columns, rows, len(rows), column_types)
