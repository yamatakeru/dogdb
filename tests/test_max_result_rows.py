from __future__ import annotations

import sqlite3

import dogdb
import duckdb
import pytest

from dogdb.adapters import DuckDBAdapter, SQLiteAdapter
from dogdb.adapters.base import RowCapExceeded, materialize_with_row_cap


class _NoRowsCursor:
    description = None
    rowcount = 1

    def fetchmany(self, _size: int):
        raise AssertionError("fetchmany must not be called without a result description")


class _NoRowsConnection:
    def execute(self, _sql: str):
        return _NoRowsCursor()


@pytest.mark.parametrize("adapter_type", [SQLiteAdapter, DuckDBAdapter])
def test_row_cap_does_not_interrupt_statements_without_rows(adapter_type):
    result = adapter_type(_NoRowsConnection()).execute("update t", row_cap=1)

    assert result.columns == []
    assert result.rows == []
    assert result.rowcount == 1


class _TrackingCursor:
    description = (("id", None, None, None, None, None, None),)
    rowcount = -1

    def __init__(self, rows: int) -> None:
        self.rows = [(index,) for index in range(rows)]
        self.offset = 0
        self.fetch_sizes: list[int] = []

    def fetchmany(self, size: int):
        self.fetch_sizes.append(size)
        batch = self.rows[self.offset : self.offset + size]
        self.offset += len(batch)
        return batch


def test_row_cap_limits_each_fetchmany_batch_to_the_remaining_observation_window():
    cursor = _TrackingCursor(2_000)

    with pytest.raises(RowCapExceeded):
        materialize_with_row_cap(cursor, row_cap=1_001)

    assert cursor.fetch_sizes == [1_000, 2]
    assert cursor.offset == 1_002


def _database(backend: str, *, rows: int = 3):
    raw = (
        sqlite3.connect(":memory:")
        if backend == "sqlite"
        else duckdb.connect(":memory:")
    )
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(index,) for index in range(rows)])
    return raw


@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
@pytest.mark.parametrize("row_cap", [3, 4])
def test_max_result_rows_returns_all_rows_at_or_below_the_limit(backend, row_cap):
    conn = dogdb.wrap(_database(backend), seed=42, max_result_rows=row_cap)

    assert conn.execute("select id from t order by id").fetchall() == [
        (0,),
        (1,),
        (2,),
    ]
    assert conn.dolly.log() == []


@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
def test_max_result_rows_raises_without_returning_partial_rows(backend):
    conn = dogdb.wrap(_database(backend), seed=42, max_result_rows=2)
    result = None

    with pytest.raises(dogdb.DollyLimitError) as caught:
        result = conn.execute("select id from t order by id").fetchall()

    assert result is None
    assert caught.value.retryable is False
    assert caught.value.category is None
    assert caught.value.severity is None
    event = conn.dolly.log()[-1]
    assert caught.value.event_id == event.event_id
    assert event.event_type == "limit_exceeded"
    assert event.outcome == "error"
    assert event.details == {
        "limit": "max_result_rows",
        "configured": 2,
        "observed": "exceeded",
    }


def test_max_result_rows_debug_does_not_record_decision_evaluated_on_interrupt():
    conn = dogdb.wrap(
        _database("sqlite"), seed=42, max_result_rows=2, debug=True
    )

    with pytest.raises(dogdb.DollyLimitError):
        conn.execute("select id from t order by id")

    assert [event.event_type for event in conn.dolly.log()] == ["limit_exceeded"]


def test_max_result_rows_interrupt_advances_occurrence_mood_and_auto_return():
    raw = _database("sqlite", rows=2)
    conn = dogdb.wrap(
        raw,
        seed=42,
        session_id="result-limit-clock",
        faults={"STASH": 1},
        max_result_rows=2,
        mood={"epoch_length": 100},
        auto_return=(1, 1),
    )
    conn.execute("select id from t order by id").fetchall()
    assert len(conn.dolly.house()) == 1
    raw.execute("insert into t values (2)")

    with pytest.raises(dogdb.DollyLimitError):
        conn.execute("select id from t order by id")

    events = conn.dolly.log()
    limit = next(event for event in events if event.event_type == "limit_exceeded")
    returned = next(event for event in events if event.event_type == "treasure_returned")
    assert limit.occurrence == 2
    assert conn._logical_tick == 2
    assert conn._mood.tick == 2
    assert conn._auto_return.current_tick == 2
    assert returned.seq < limit.seq
    assert conn.dolly.house() == []


def test_max_result_rows_evaluates_bark_before_sending_the_query_to_backend():
    raw = _database("sqlite")
    statements: list[str] = []
    raw.set_trace_callback(statements.append)
    conn = dogdb.wrap(
        raw,
        seed=42,
        faults={"BARK": 1},
        max_result_rows=2,
    )

    with pytest.raises(dogdb.DollyBarkError):
        conn.execute("select id from t order by id")

    assert statements == []
    assert [event.event_type for event in conn.dolly.log()] == ["fault_injected"]
    assert all(
        event.details.get("limit") != "max_result_rows"
        for event in conn.dolly.log()
    )


def test_max_result_rows_and_max_intervention_rows_are_independent():
    intervention_limited = dogdb.wrap(
        _database("sqlite"),
        seed=42,
        max_result_rows=10,
        max_intervention_rows=2,
    )
    assert len(
        intervention_limited.execute("select id from t order by id").fetchall()
    ) == 3
    assert intervention_limited.dolly.log()[-1].details["limit"] == (
        "max_intervention_rows"
    )

    result_limited = dogdb.wrap(
        _database("sqlite"),
        seed=42,
        max_result_rows=2,
        max_intervention_rows=10,
    )
    with pytest.raises(dogdb.DollyLimitError):
        result_limited.execute("select id from t order by id")
    assert result_limited.dolly.log()[-1].details["limit"] == "max_result_rows"

    dogdb.wrap(
        _database("sqlite"),
        seed=42,
        max_result_rows=100,
        max_intervention_rows=100_000,
    )


def test_max_result_rows_respects_select_table_scope():
    conn = dogdb.wrap(
        _database("sqlite"),
        seed=42,
        max_result_rows=1,
        only_tables=["other_table"],
    )

    assert len(conn.execute("select id from t order by id").fetchall()) == 3
    assert conn.dolly.log() == []


def test_max_result_rows_interrupt_is_deterministic_for_identical_runs():
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            _database("sqlite"),
            seed=42,
            session_id="result-limit-replay",
            max_result_rows=2,
        )
        with pytest.raises(dogdb.DollyLimitError):
            conn.execute("select id from t order by id")
        runs.append(conn.dolly.log())

    assert runs[0] == runs[1]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_max_result_rows_requires_a_positive_integer(value):
    with pytest.raises(ValueError, match="max_result_rows"):
        dogdb.wrap(_database("sqlite"), seed=42, max_result_rows=value)
