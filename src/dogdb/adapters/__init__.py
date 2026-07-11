"""Backend adapters."""

from dogdb.adapters.duckdb import DuckDBAdapter
from dogdb.adapters.sqlite import SQLiteAdapter

__all__ = ["DuckDBAdapter", "SQLiteAdapter"]
