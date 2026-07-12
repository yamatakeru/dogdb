from __future__ import annotations

import sqlite3
from typing import Any

import pytest

import dogdb


class TrackingSQLiteConnection(sqlite3.Connection):
    native_accesses: dict[str, int]

    def __getattribute__(self, name: str) -> Any:
        if name in {"cursor", "interrupt"}:
            accesses = super().__getattribute__("native_accesses")
            accesses[name] = accesses.get(name, 0) + 1
        return super().__getattribute__(name)


TrackingSQLiteConnection.__module__ = "sqlite3"


class NativeCallable:
    def __call__(self) -> str:
        return "native result"


class TrackingDuckDBConnection:
    def __init__(self) -> None:
        self.native_accesses: dict[str, int] = {}
        self.native_callable = NativeCallable()

    def __getattribute__(self, name: str) -> Any:
        if name in {"cursor", "interrupt", "sql"}:
            accesses = object.__getattribute__(self, "native_accesses")
            accesses[name] = accesses.get(name, 0) + 1
        return object.__getattribute__(self, name)

    def cursor(self) -> None:
        raise AssertionError("native cursor must not be reached")

    def interrupt(self) -> None:
        raise AssertionError("native interrupt must not be reached")

    def sql(self, query: str) -> None:
        raise AssertionError("native sql must not be reached")


def _tracking_sqlite() -> TrackingSQLiteConnection:
    raw = sqlite3.connect(":memory:", factory=TrackingSQLiteConnection)
    raw.native_accesses = {}
    return raw


def test_fail_closed_duckdb_cursor_does_not_reach_native_connection():
    raw = TrackingDuckDBConnection()
    conn = dogdb.wrap(raw, seed=42)

    with pytest.raises(AttributeError) as error:
        _ = conn.cursor

    message = str(error.value)
    assert "cannot inject faults" in message
    assert "execute()" in message
    assert "allow_native_passthrough=True" in message
    assert raw.native_accesses.get("cursor", 0) == 0


def test_sqlite_cursor_uses_proxy_without_reaching_native_connection():
    raw = _tracking_sqlite()
    conn = dogdb.wrap(raw, seed=42)

    cursor = conn.cursor()

    assert type(cursor).__name__ == "CursorProxy"
    assert raw.native_accesses.get("cursor", 0) == 0
    raw.close()


def test_fail_closed_duckdb_sql_does_not_reach_native_connection():
    raw = TrackingDuckDBConnection()
    conn = dogdb.wrap(raw, seed=42)

    with pytest.raises(AttributeError) as error:
        _ = conn.sql

    message = str(error.value)
    assert "cannot inject faults" in message
    assert "execute()" in message
    assert "allow_native_passthrough=True" in message
    assert raw.native_accesses.get("sql", 0) == 0


@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
def test_fail_closed_unknown_attribute_does_not_reach_native_connection(
    backend: str,
):
    raw = _tracking_sqlite() if backend == "sqlite" else TrackingDuckDBConnection()
    conn = dogdb.wrap(raw, seed=42)

    with pytest.raises(AttributeError) as error:
        _ = conn.interrupt

    assert "Supported public API" in str(error.value)
    assert "allow_native_passthrough=True" in str(error.value)
    assert raw.native_accesses.get("interrupt", 0) == 0
    if backend == "sqlite":
        raw.close()


def test_native_passthrough_keeps_sqlite_cursor_on_injected_surface():
    raw = sqlite3.connect(":memory:")
    conn = dogdb.wrap(raw, seed=42, allow_native_passthrough=True)

    cursor = conn.cursor()

    assert type(cursor).__name__ == "CursorProxy"
    assert conn.dolly.stats()["escape_hatches"].get("cursor", 0) == 0
    conn.close()


def test_native_passthrough_hasattr_does_not_count_call():
    raw = sqlite3.connect(":memory:")
    conn = dogdb.wrap(raw, seed=42, allow_native_passthrough=True)

    assert hasattr(conn, "cursor")
    assert conn.dolly.stats()["escape_hatches"].get("cursor", 0) == 0
    conn.close()


def test_native_passthrough_aggregates_undeclared_callable_calls():
    raw = sqlite3.connect(":memory:")
    conn = dogdb.wrap(raw, seed=42, allow_native_passthrough=True)

    conn.interrupt()

    assert conn.dolly.stats()["escape_hatches"]["other"] == 1
    conn.close()


def test_native_passthrough_accepts_callable_objects_without_function_metadata():
    conn = dogdb.wrap(
        TrackingDuckDBConnection(), seed=42, allow_native_passthrough=True
    )

    assert conn.native_callable() == "native result"
    assert conn.dolly.stats()["escape_hatches"]["other"] == 1
