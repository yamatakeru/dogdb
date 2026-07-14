"""Backend adapters."""

from dogdb.adapters.sqlite import SQLiteAdapter


def __getattr__(name):
    if name == "DuckDBAdapter":
        from dogdb.adapters.duckdb import DuckDBAdapter
        return DuckDBAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["DuckDBAdapter", "SQLiteAdapter"]
