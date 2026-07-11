from __future__ import annotations

import sqlite3


def raw_integer_connection(rows: int, *, start: int = 0) -> sqlite3.Connection:
    """Create an SQLite table populated with a contiguous integer range."""

    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany(
        "insert into t values (?)", [(index,) for index in range(start, start + rows)]
    )
    return raw


def raw_three_row_connection() -> sqlite3.Connection:
    """Create the shared three-row table with IDs 1, 2, and 3."""

    return raw_integer_connection(3, start=1)
