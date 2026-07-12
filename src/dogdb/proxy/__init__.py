"""DB-API proxy surface."""

from dogdb.proxy.connection import (
    CursorProxy,
    DBAPIProxy,
    DuckDBProxy,
    SQLiteProxy,
    connect,
    wrap,
)

__all__ = [
    "CursorProxy",
    "DBAPIProxy",
    "DuckDBProxy",
    "SQLiteProxy",
    "connect",
    "wrap",
]
