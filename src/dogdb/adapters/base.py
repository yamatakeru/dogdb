"""Shared adapter helpers."""

from __future__ import annotations

from typing import Any

from dogdb.core.models import LogicalResult


def materialize(cursor: Any) -> LogicalResult:
    description = cursor.description
    if description is None:
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))
    columns = [str(column[0]) for column in description]
    rows = [tuple(row) for row in cursor.fetchall()]
    return LogicalResult(columns, rows, len(rows))
