from __future__ import annotations

import ast
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
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
    raw.execute("create table t(id integer, text_value varchar, amount double)")
    raw.executemany(
        "insert into t values (?, ?, ?)",
        [(1, "alpha", 1.25), (2, "beta", 2.5), (3, "gamma", 3.75)],
    )
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


@pytest.mark.parametrize(
    ("fault", "sql", "options"),
    [
        ("ECHO", "select id from t order by id", {}),
        (
            "TAIL_CHASE",
            "select id from t order by id",
            {"tail_chase_mode": "silent"},
        ),
        ("FALSE_EMPTY", "select id from t order by id", {}),
        ("PAGE_HOLE", "select id from t order by id limit 2 offset 1", {}),
    ],
)
def test_backends_produce_matching_shape_fault_events(fault, sql, options):
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id=f"shape-{fault}",
            faults={fault: 1},
            **options,
        )
        conn.execute(sql).fetchall()
        signatures.append(
            [
                (event.fault, event.decision_key, event.outcome, event.details)
                for event in conn.dolly.log()
            ]
        )
        assert conn.dolly.house() == []
    assert signatures[0] == signatures[1]


@pytest.mark.parametrize(
    ("fault", "sql", "options"),
    [
        (
            "CHEW",
            "select text_value from t order by id",
            {"chew_profiles": ("utf8_truncate",)},
        ),
        ("TANGLED_LEASH", "select id, text_value from t order by id", {}),
        ("WRONG_COUNT", "select id from t order by id", {}),
    ],
)
def test_backends_produce_matching_value_fault_events(fault, sql, options):
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id=f"value-{fault}",
            faults={fault: 1},
            **options,
        )
        conn.execute(sql).fetchall()
        signatures.append(
            [
                (event.fault, event.decision_key, event.outcome, event.details)
                for event in conn.dolly.log()
            ]
        )
        assert conn.dolly.house() == []
    assert signatures[0] == signatures[1]


@pytest.mark.parametrize(
    ("fault", "error_type", "options"),
    [
        ("SLOTH", None, {"clock": lambda _: None}),
        ("BARK", dogdb.DollyBarkError, {}),
        ("GUARD_BOWL", dogdb.DollyBusyError, {}),
        ("NO_DROP", dogdb.DollyNoDropError, {}),
    ],
)
def test_backends_produce_matching_availability_fault_events(
    fault, error_type, options
):
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id=f"availability-{fault}",
            faults={fault: 1},
            **options,
        )
        if error_type is None:
            conn.execute("select id from t order by id").fetchall()
        else:
            with pytest.raises(error_type):
                conn.execute("select id from t order by id")
        signatures.append(
            [
                (
                    event.event_type,
                    event.fault,
                    event.decision_key,
                    event.outcome,
                    event.details,
                )
                for event in conn.dolly.log()
            ]
        )
    assert signatures[0] == signatures[1]


def test_backends_produce_matching_mood_event_sequences():
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id="mood-conformance",
            faults={"ECHO": 0.4},
            mood={"epoch_length": 2},
        )
        for _ in range(10):
            conn.execute("select id from t order by id").fetchall()
        signatures.append(conn.dolly.log())
    assert signatures[0] == signatures[1]


def test_backends_produce_matching_auto_return_event_sequences():
    signatures = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id="auto-return-conformance",
            faults={"STASH": 1},
            auto_return=(1, 1),
        )
        conn.execute("select id from t order by id").fetchall()
        conn.execute("create table trigger_auto(x integer)")
        signatures.append(conn.dolly.log())
    assert signatures[0] == signatures[1]


def test_backends_produce_matching_old_bone_events_and_stats():
    signatures = []
    stats = []
    for backend in ("duckdb", "sqlite"):
        conn = dogdb.wrap(
            _populated(backend),
            seed=42,
            session_id="old-bone-conformance",
            faults={"OLD_BONE": 1},
        )
        conn.execute("select text_value from t order by id").fetchall()
        conn.execute("update t set text_value = 'updated' where id = 1")
        conn.execute("select text_value from t order by id").fetchall()
        signatures.append(conn.dolly.log())
        stats.append(conn.dolly.stats())
    assert signatures[0] == signatures[1]
    assert stats[0] == stats[1]


class _TypedCursor:
    description = (("tz",), ("amount",), ("payload",))
    rowcount = -1

    def fetchall(self):
        return [
            (
                datetime(2026, 7, 12, 12, 30, tzinfo=timezone.utc),
                Decimal("123.45"),
                b"\x00\xff",
            )
        ]


class _TypedConnection:
    in_transaction = False

    def execute(self, sql, params=None):
        return _TypedCursor()

    def close(self):
        pass


@pytest.mark.parametrize("adapter", [DuckDBAdapter, SQLiteAdapter])
def test_common_adapter_suite_preserves_timezone_decimal_and_blob(adapter):
    result = adapter(_TypedConnection()).execute("select typed values")

    assert isinstance(result.rows[0][0], datetime)
    assert result.rows[0][0].tzinfo is timezone.utc
    assert result.rows[0][1] == Decimal("123.45")
    assert result.rows[0][2] == b"\x00\xff"


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
