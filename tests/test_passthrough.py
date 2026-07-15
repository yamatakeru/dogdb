from __future__ import annotations

import sqlite3
import warnings

import pytest

import dogdb
from dogdb.core.fingerprints import template_fingerprint
from dogdb.core.models import LogicalResult


class _ConformingString(str):
    def __conform__(self, protocol):
        return str(self)


def _connection(*, on_passthrough: str | None = None):
    options = {} if on_passthrough is None else {"on_passthrough": on_passthrough}
    return dogdb.wrap(sqlite3.connect(":memory:"), seed=42, **options)


def _exercise_target(conn, target: str) -> None:
    if target == "named_parameters":
        conn.execute("select :value", {"value": 7}).fetchall()
    elif target == "unknown_sql":
        conn.execute("pragma user_version").fetchall()
    elif target == "unsupported_parameter_type":
        conn.execute("select ?", (_ConformingString("bone"),)).fetchall()
    else:  # pragma: no cover - test helper guard
        raise AssertionError(f"unknown target: {target}")


@pytest.mark.parametrize(
    ("reason", "operation"),
    [
        (
            "named_parameters",
            lambda conn: conn.execute("select :value", {"value": 7}).fetchall(),
        ),
        ("unknown_sql", lambda conn: conn.execute("pragma user_version").fetchall()),
        (
            "transaction_statement",
            lambda conn: (conn.execute("begin"), conn.rollback()),
        ),
        (
            "unsupported_parameter_type",
            lambda conn: conn.execute(
                "select ?", (_ConformingString("bone"),)
            ).fetchall(),
        ),
        (
            "executemany",
            lambda conn: (
                conn.execute("create table t(value integer)"),
                conn.executemany("insert into t values (?)", [(1,), (2,)]),
            ),
        ),
    ],
)
def test_all_passthrough_reasons_are_recorded_in_sparse_snapshot(reason, operation):
    conn = _connection()

    operation(conn)

    assert conn.dolly.stats()["passthrough"] == {reason: 1}
    assert conn.dolly.log() == []


@pytest.mark.parametrize(
    "target",
    ["named_parameters", "unknown_sql", "unsupported_parameter_type"],
)
@pytest.mark.parametrize("mode", [None, "allow"])
def test_allow_and_default_modes_silently_execute_targeted_passthrough(target, mode):
    conn = _connection(on_passthrough=mode)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _exercise_target(conn, target)

    assert conn.dolly.stats()["passthrough"] == {target: 1}


@pytest.mark.parametrize(
    "target",
    ["named_parameters", "unknown_sql", "unsupported_parameter_type"],
)
def test_warn_mode_emits_public_dogdb_warning_and_executes(target):
    conn = _connection(on_passthrough="warn")

    with pytest.warns(dogdb.DollyPassthroughWarning, match=target):
        _exercise_target(conn, target)

    assert conn.dolly.stats()["passthrough"] == {target: 1}


@pytest.mark.parametrize(
    "target",
    ["named_parameters", "unknown_sql", "unsupported_parameter_type"],
)
def test_error_mode_records_then_blocks_targeted_passthrough(target):
    conn = _connection(on_passthrough="error")

    with pytest.raises(dogdb.DollyPassthroughError, match=target) as caught:
        _exercise_target(conn, target)

    assert caught.value.retryable is False
    with pytest.raises(AttributeError):
        caught.value.retryable = True
    assert not isinstance(caught.value, dogdb.DogDBError)
    assert conn.dolly.stats()["passthrough"] == {target: 1}
    assert conn.dolly.log() == []


@pytest.mark.parametrize("mode", ["allow", "warn", "error"])
@pytest.mark.parametrize("reason", ["transaction_statement", "executemany"])
def test_non_triggering_reasons_are_always_silent_passthrough(mode, reason):
    conn = _connection(on_passthrough=mode)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        if reason == "transaction_statement":
            conn.execute("begin")
            conn.rollback()
        else:
            conn.execute("create table t(value integer)")
            conn.executemany("insert into t values (?)", [(1,), (2,)])

    assert conn.dolly.stats()["passthrough"] == {reason: 1}


def test_error_mode_blocks_named_insert_before_backend_execution():
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(value integer)")
    conn = dogdb.wrap(raw, seed=42, on_passthrough="error")

    with pytest.raises(dogdb.DollyPassthroughError):
        conn.execute("insert into t values (:value)", {"value": 7})

    assert raw.execute("select count(*) from t").fetchone() == (0,)


def test_wrap_rejects_unknown_passthrough_mode_before_wrapping():
    raw = sqlite3.connect(":memory:")

    with pytest.raises(ValueError, match="on_passthrough"):
        dogdb.wrap(raw, seed=42, on_passthrough="block")

    assert raw.execute("select 1").fetchone() == (1,)


def test_passthrough_reason_priority_matches_historical_early_return_order(
    monkeypatch,
):
    named_over_unknown = _connection(on_passthrough="error")
    with pytest.raises(dogdb.DollyPassthroughError, match="named_parameters"):
        named_over_unknown.execute("pragma user_version", {})

    unknown_over_unsupported = _connection(on_passthrough="error")
    with pytest.raises(dogdb.DollyPassthroughError, match="unknown_sql"):
        unknown_over_unsupported.execute(
            "pragma user_version", (_ConformingString("bone"),)
        )

    transaction_over_unsupported = _connection(on_passthrough="error")
    reached_backend = []

    def capture_execute(sql, params):
        reached_backend.append((sql, params))
        return LogicalResult([], [], -1)

    monkeypatch.setattr(transaction_over_unsupported._adapter, "execute", capture_execute)
    params = (_ConformingString("bone"),)
    transaction_over_unsupported.execute("begin", params)

    assert reached_backend == [("begin", params)]
    assert transaction_over_unsupported.dolly.stats()["passthrough"] == {
        "transaction_statement": 1
    }


def test_stats_snapshot_existing_shape_is_unchanged_without_passthrough():
    conn = _connection()
    sql = "select 1"

    conn.execute(sql).fetchall()
    stats = conn.dolly.stats()

    assert set(stats) == {
        "sqlglot_version",
        "fingerprints",
        "escape_hatches",
        "passthrough",
        "totals",
    }
    assert stats["fingerprints"] == {
        template_fingerprint(sql): {
            "select": 1,
            "unknown": 0,
            "interventions": 0,
        }
    }
    assert stats["escape_hatches"] == {"other": 0}
    assert stats["passthrough"] == {}
    assert stats["totals"] == {"select": 1, "unknown": 0, "interventions": 0}
