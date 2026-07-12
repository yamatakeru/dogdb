from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import duckdb

import dogdb
from dogdb.proxy import DuckDBProxy, SQLiteProxy


def _event_signature(connection: DuckDBProxy) -> list[tuple[Any, ...]]:
    return [
        (
            event.decision_key,
            event.event_type,
            event.fault,
            event.phase,
            event.outcome,
            event.details,
        )
        for event in connection.dolly.log()
    ]


def test_duckdb_cursor_clones_share_decisions_and_events():
    observations = []
    sql = "select * from (values (1), (2), (3)) as t(id)"
    for alternate_clone in (False, True):
        connection = dogdb.wrap(
            duckdb.connect(":memory:"),
            seed=42,
            session_id="duckdb-cursor-clone",
            faults={"SHUFFLE": 1},
        )
        assert isinstance(connection, DuckDBProxy)
        clone = connection.cursor()
        results = []
        for index in range(4):
            surface = clone if alternate_clone and index % 2 else connection
            results.append(surface.execute(sql).fetchall())
        observations.append((results, _event_signature(connection)))
        clone.close()
        connection.close()

    assert observations[0] == observations[1]


def test_duckdb_cursor_stash_and_close_share_only_intervention_core():
    connection = dogdb.wrap(
        duckdb.connect(":memory:"), seed=42, faults={"STASH": 1}
    )
    assert isinstance(connection, DuckDBProxy)

    with connection.cursor() as clone:
        nested = clone.cursor()
        nested.close()
        clone.execute("select * from (values (1), (2), (3)) as t(id)")

    assert len(connection.dolly.house()) == 1
    assert [event.fault for event in connection.dolly.log()] == ["STASH"]
    assert connection.execute("select 1").fetchall() == []
    assert [event.fault for event in connection.dolly.log()] == ["STASH", "STASH"]
    connection.close()


def test_description_matches_native_duckdb_and_sqlite():
    duckdb_sql = "select 1::integer as id, 'x'::varchar as label"
    native_duckdb = duckdb.connect(":memory:")
    wrapped_duckdb = dogdb.wrap(duckdb.connect(":memory:"), seed=42, faults={})
    assert isinstance(wrapped_duckdb, DuckDBProxy)

    native_duckdb.execute(duckdb_sql)
    wrapped_duckdb.execute(duckdb_sql)
    assert wrapped_duckdb.description == native_duckdb.description

    native_clone = native_duckdb.cursor()
    wrapped_clone = wrapped_duckdb.cursor()
    native_clone.execute(duckdb_sql)
    wrapped_clone.execute(duckdb_sql)
    assert wrapped_clone.description == native_clone.description

    sqlite_sql = "select 1 as id, 'x' as label"
    native_sqlite = sqlite3.connect(":memory:")
    wrapped_sqlite = dogdb.wrap(sqlite3.connect(":memory:"), seed=42, faults={})
    assert isinstance(wrapped_sqlite, SQLiteProxy)
    native_cursor = native_sqlite.execute(sqlite_sql)
    wrapped_cursor = wrapped_sqlite.execute(sqlite_sql)
    assert wrapped_cursor.description == native_cursor.description
    description = wrapped_cursor.description
    assert description is not None
    assert all(column[1:] == (None,) * 6 for column in description)

    native_clone.close()
    wrapped_clone.close()
    native_duckdb.close()
    wrapped_duckdb.close()
    native_sqlite.close()
    wrapped_sqlite.close()


def test_tangled_leash_keeps_duckdb_types_in_column_positions():
    sql = "select 1::integer as first, 'x'::varchar as second"
    native = duckdb.connect(":memory:")
    wrapped = dogdb.wrap(
        duckdb.connect(":memory:"), seed=42, faults={"TANGLED_LEASH": 1}
    )
    assert isinstance(wrapped, DuckDBProxy)

    native.execute(sql)
    wrapped.execute(sql)

    wrapped_description = wrapped.description
    native_description = native.description
    assert wrapped_description is not None
    assert native_description is not None
    assert [column[0] for column in wrapped_description] == ["second", "first"]
    assert [column[1] for column in wrapped_description] == [
        column[1] for column in native_description
    ]
    assert wrapped.fetchall() == native.fetchall()
    native.close()
    wrapped.close()


def _observe_uncommitted_insert(path: Path, *, wrapped: bool) -> list[tuple[Any, ...]]:
    native = duckdb.connect(str(path))
    connection: Any = dogdb.wrap(native, seed=42, faults={}) if wrapped else native
    connection.execute("create table t(id integer)")
    connection.execute("begin transaction")
    connection.execute("insert into t values (1)")
    clone = connection.cursor()
    try:
        return clone.execute("select id from t").fetchall()
    finally:
        clone.close()
        connection.rollback()
        connection.close()


def test_duckdb_cursor_transaction_isolation_matches_native(tmp_path: Path):
    native_rows = _observe_uncommitted_insert(tmp_path / "native.duckdb", wrapped=False)
    wrapped_rows = _observe_uncommitted_insert(
        tmp_path / "wrapped.duckdb", wrapped=True
    )

    assert wrapped_rows == native_rows
