"""SQLite adapter using only Python's standard library backend."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from dogdb.adapters.base import materialize_with_row_cap
from dogdb.core.models import LogicalResult


class SQLiteAdapter:
    sql_capable_attrs: frozenset[str] = frozenset(
        {"cursor", "execute", "executemany", "executescript"}
    )

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        row_cap: int | None = None,
    ) -> LogicalResult:
        cursor = self.connection.execute(sql, params) if params else self.connection.execute(sql)
        return materialize_with_row_cap(cursor, row_cap=row_cap)

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> LogicalResult:
        cursor = self.connection.executemany(sql, params)
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))

    def close(self) -> None:
        self.connection.close()

    @property
    def in_transaction(self) -> bool:
        return self.connection.in_transaction
