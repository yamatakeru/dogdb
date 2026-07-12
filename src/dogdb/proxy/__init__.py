"""DB-API proxy surface."""

from dogdb.proxy.connection import (
    CursorProxy,
    DuckDBProxy,
    SQLiteProxy,
    connect,
    wrap,
)

__all__ = [
    "CursorProxy",
    "DuckDBProxy",
    "SQLiteProxy",
    "connect",
    "wrap",
]
