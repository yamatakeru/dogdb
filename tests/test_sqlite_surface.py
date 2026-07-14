from __future__ import annotations

import sqlite3

import pytest

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    duckdb = None
    HAS_DUCKDB = False

import dogdb
from dogdb.proxy import CursorProxy, DuckDBProxy, SQLiteProxy


def _populated() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, name text)")
    raw.executemany(
        "insert into t values (?, ?)",
        [(1, "alpha"), (2, "beta"), (3, "gamma")],
    )
    raw.commit()
    return raw


@pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb not installed")
def test_wrap_selects_backend_faithful_proxy_class():
    sqlite_proxy = dogdb.wrap(sqlite3.connect(":memory:"), seed=1)
    duckdb_proxy = dogdb.wrap(duckdb.connect(":memory:"), seed=1)

    assert isinstance(sqlite_proxy, SQLiteProxy)
    assert isinstance(duckdb_proxy, DuckDBProxy)
    assert duckdb_proxy.execute("select 1") is duckdb_proxy

    sqlite_proxy.close()
    duckdb_proxy.close()


def test_execute_and_executemany_return_independent_cursors():
    conn = dogdb.wrap(_populated(), seed=1)

    first = conn.execute("select 1")
    second = conn.execute("select 2")
    conn.execute("create table inserted(id integer)")
    many = conn.executemany("insert into inserted values (?)", [(1,), (2,)])

    assert isinstance(first, CursorProxy)
    assert first is not second
    assert first.fetchall() == [(1,)]
    assert second.fetchall() == [(2,)]
    assert many.rowcount == 2
    conn.close()


def test_cursor_shortcut_and_cursor_execute_have_same_surface():
    conn = dogdb.wrap(_populated(), seed=1)
    explicit = conn.cursor()

    assert isinstance(explicit, CursorProxy)
    assert explicit.description is None
    assert explicit.rowcount == -1
    assert explicit.execute("select id from t order by id") is explicit
    shortcut = conn.execute("select id from t order by id")
    assert explicit.fetchall() == shortcut.fetchall() == [(1,), (2,), (3,)]
    conn.close()


def test_iteration_and_fetch_methods_share_consumption_position():
    conn = dogdb.wrap(_populated(), seed=1)
    cursor = conn.execute("select id from t order by id")

    assert next(iter(cursor)) == (1,)
    assert cursor.fetchmany(1) == [(2,)]
    assert cursor.fetchone() == (3,)
    assert cursor.fetchall() == []
    assert cursor.fetchone() is None
    conn.close()


@pytest.mark.parametrize(
    "attribute", ["fetchall", "fetchone", "fetchmany", "description", "rowcount"]
)
def test_connection_level_result_access_is_rejected_with_migration_hint(attribute):
    conn = dogdb.wrap(sqlite3.connect(":memory:"), seed=1)

    with pytest.raises(AttributeError, match=r"conn\.execute\(sql\)\.fetchall\(\)"):
        getattr(conn, attribute)
    conn.close()


def test_sqlite_executescript_remains_fail_closed():
    conn = dogdb.wrap(sqlite3.connect(":memory:"), seed=1)

    with pytest.raises(AttributeError) as caught:
        conn.executescript("select 1")

    message = str(caught.value)
    assert "cannot inject faults" in message
    assert "execute()" in message
    assert "allow_native_passthrough=True" in message
    conn.close()


def test_sqlite_context_manager_commits_without_closing(tmp_path):
    path = tmp_path / "commit.sqlite"
    raw = sqlite3.connect(path)
    raw.execute("create table t(id integer)")
    raw.commit()
    conn = dogdb.wrap(raw, seed=1)

    with conn:
        conn.execute("insert into t values (1)")

    observer = sqlite3.connect(path)
    assert observer.execute("select id from t").fetchall() == [(1,)]
    assert conn.execute("select id from t").fetchall() == [(1,)]
    observer.close()
    conn.close()


def test_sqlite_context_manager_rolls_back_without_closing(tmp_path):
    path = tmp_path / "rollback.sqlite"
    raw = sqlite3.connect(path)
    raw.execute("create table t(id integer)")
    raw.commit()
    conn = dogdb.wrap(raw, seed=1)

    with pytest.raises(RuntimeError, match="rollback"):
        with conn:
            conn.execute("insert into t values (1)")
            raise RuntimeError("rollback")

    assert conn.execute("select id from t").fetchall() == []
    conn.close()


def _surface_observations(connection):
    first = connection.execute("select id, name from t order by id")
    second = connection.execute("select id from t where id = 3")
    first_row = next(iter(first))
    remaining = first.fetchmany(1) + first.fetchall()
    return {
        "independent": first is not second,
        "first_row": first_row,
        "remaining": remaining,
        "second_rows": second.fetchall(),
        "description": first.description,
        "rowcount": first.rowcount,
    }


def test_calm_sqlite_proxy_matches_native_surface_operations():
    native = _populated()
    wrapped = dogdb.wrap(_populated(), seed=1, faults={})

    assert _surface_observations(wrapped) == _surface_observations(native)

    native.close()
    wrapped.close()


def test_cursor_and_connection_shortcut_share_decisions_and_events():
    signatures = []
    for use_cursor in (False, True):
        conn = dogdb.wrap(
            _populated(),
            seed=42,
            session_id="sqlite-entrypoint",
            faults={"SHUFFLE": 1},
        )
        cursor = conn.cursor() if use_cursor else None
        result = (
            cursor.execute("select id from t").fetchall()
            if cursor is not None
            else conn.execute("select id from t").fetchall()
        )
        signatures.append(
            (
                result,
                [
                    (event.decision_key, event.fault, event.outcome)
                    for event in conn.dolly.log()
                ],
            )
        )
        conn.close()

    assert signatures[0] == signatures[1]
