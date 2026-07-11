from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import duckdb
import pytest

import dogdb
from dogdb.adapters import DuckDBAdapter, SQLiteAdapter


def _backend(name: str):
    if name == "duckdb":
        return duckdb.connect(":memory:")
    return sqlite3.connect(":memory:")


def _populated(name: str):
    raw = _backend(name)
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    return raw


def test_core_has_no_backend_imports():
    core = Path(__file__).parents[1] / "src" / "dogdb" / "core"
    forbidden = []
    for path in core.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                forbidden.extend(
                    name.name for name in node.names if name.name in {"duckdb", "sqlite3"}
                )
            elif isinstance(node, ast.ImportFrom) and node.module in {"duckdb", "sqlite3"}:
                forbidden.append(node.module)
    assert forbidden == []


def test_duckdb_adapter_normalizes_results():
    result = DuckDBAdapter(duckdb.connect(":memory:")).execute(
        "select 1 as x, 'a' as y"
    )
    assert result.columns == ["x", "y"]
    assert result.rows == [(1, "a")]


def test_sqlite_adapter_normalizes_results():
    result = SQLiteAdapter(sqlite3.connect(":memory:")).execute(
        "select 1 as x, 'a' as y"
    )
    assert result.columns == ["x", "y"]
    assert result.rows == [(1, "a")]


def test_backends_produce_matching_fault_events():
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id="conformance",
            faults={"SHUFFLE": 1},
        )
        conn.execute("select id from t").fetchall()
        signatures.append(
            [(event.fault, event.decision_key, event.outcome) for event in conn.dolly.log()]
        )
    assert signatures[0] == signatures[1]


def test_wrap_duckdb_and_plain_result_match_when_calm():
    conn = dogdb.wrap(duckdb.connect(":memory:"), seed=42)
    assert all(
        hasattr(conn, method)
        for method in ("execute", "fetchall", "fetchone", "fetchmany", "close")
    )
    assert conn.execute("select 1 as x").fetchall() == [(1,)]


def test_seed_is_required():
    with pytest.raises(TypeError):
        dogdb.wrap(sqlite3.connect(":memory:"))


def test_fetch_style_does_not_change_fault_application():
    all_conn = dogdb.wrap(
        _populated("sqlite"), seed=42, session_id="fetch", faults={"SHUFFLE": 1}
    )
    one_conn = dogdb.wrap(
        _populated("sqlite"), seed=42, session_id="fetch", faults={"SHUFFLE": 1}
    )
    all_rows = all_conn.execute("select id from t").fetchall()
    one_conn.execute("select id from t")
    one_rows = []
    while (row := one_conn.fetchone()) is not None:
        one_rows.append(row)
    assert all_rows == one_rows
    assert all_conn.dolly.log() == one_conn.dolly.log()


def test_executemany_is_unmodified_and_silent():
    conn = dogdb.wrap(
        sqlite3.connect(":memory:"), seed=42, faults={"IGNORE": 1, "STASH": 1}
    )
    conn._connection.execute("create table t(id integer)")
    conn.executemany("insert into t values (?)", [(1,), (2,)])
    assert conn._connection.execute("select count(*) from t").fetchone()[0] == 2
    assert conn.dolly.log() == []


def test_dolly_namespace_exposes_stashed_treasure():
    conn = dogdb.wrap(_populated("sqlite"), seed=42, faults={"STASH": 1})
    conn.execute("select id from t").fetchall()
    treasure = conn.dolly.house()[0]
    assert treasure.treasure_id and treasure.template_fingerprint
    assert isinstance(treasure.row_index, int)


def test_transactions_delegate_to_backend(tmp_path):
    path = tmp_path / "transaction.sqlite"
    raw = sqlite3.connect(path)
    raw.execute("create table t(id integer)")
    raw.commit()
    conn = dogdb.wrap(raw, seed=42, faults={"IGNORE": 1})
    conn.execute("begin")
    with pytest.raises(dogdb.DollyIgnoredError):
        conn.execute("insert into t values (1)")
    # INSERT is ignored; transaction control itself remains delegated.
    assert conn.in_transaction
    conn.rollback()
    conn._faults.policy.ignore = 0
    conn.execute("begin")
    conn.execute("insert into t values (1)")
    conn.execute("commit")
    conn.close()
    raw = sqlite3.connect(path)
    assert raw.execute("select id from t").fetchall() == [(1,)]
