"""DuckDB adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dogdb.adapters.base import materialize
from dogdb.core.models import LogicalResult


class DuckDBAdapter:
    sql_capable_attrs: frozenset[str] = frozenset(
        {"cursor", "execute", "executemany", "query", "sql", "table"}
    )

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        row_cap: int | None = None,
    ) -> LogicalResult:
        cursor = self.connection.execute(sql, params) if params else self.connection.execute(sql)
        return materialize(cursor, row_cap=row_cap)

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> LogicalResult:
        cursor = self.connection.executemany(sql, params)
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))

    def close(self) -> None:
        self.connection.close()

    @property
    def in_transaction(self) -> bool:
        return bool(getattr(self.connection, "in_transaction", False))
