from __future__ import annotations

import sqlite3

import dogdb
import pytest

from dogdb.core.models import LogicalResult


def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    return raw


def test_sloth_uses_injected_clock_and_consumes_fault_slot():
    sleeps: list[float] = []
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="sloth",
        faults={"SLOTH": 1, "ECHO": 1},
        clock=sleeps.append,
        sloth_max_delay_ms=250,
    )

    rows = conn.execute("select id from t order by id").fetchall()
    event = conn.dolly.log()[0]

    assert rows == [(1,), (2,), (3,)]
    assert [item.fault for item in conn.dolly.log()] == ["SLOTH"]
    assert event.outcome == "delayed"
    assert 1 <= event.details["delay_ms"] <= 250
    assert sleeps == [event.details["delay_ms"] / 1_000]


def test_sloth_delay_and_event_are_deterministic():
    runs = []
    for _ in range(2):
        sleeps: list[float] = []
        conn = dogdb.wrap(
            _raw(),
            seed=42,
            session_id="sloth-replay",
            faults={"SLOTH": 1},
            clock=sleeps.append,
        )
        rows = conn.execute("select id from t order by id").fetchall()
        runs.append((rows, sleeps, conn.dolly.log()))
    assert runs[0] == runs[1]


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_sloth_delay_bound_must_be_a_positive_integer(value):
    with pytest.raises(ValueError, match="sloth_max_delay_ms"):
        dogdb.wrap(_raw(), seed=42, sloth_max_delay_ms=value)


def test_clock_must_be_callable():
    with pytest.raises(ValueError, match="clock must be callable"):
        dogdb.wrap(_raw(), seed=42, clock=None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("fault", "error_type"),
    [
        ("BARK", dogdb.DollyBarkError),
        ("GUARD_BOWL", dogdb.DollyBusyError),
    ],
)
def test_before_execute_errors_do_not_change_backend(fault, error_type):
    raw = _raw()
    conn = dogdb.wrap(raw, seed=42, faults={fault: 1})

    with pytest.raises(error_type) as caught:
        conn.execute("insert into t values (4)")

    assert caught.value.outcome == "not_executed"
    assert caught.value.retryable is True
    assert raw.execute("select id from t order by id").fetchall() == [(1,), (2,), (3,)]
    assert conn.dolly.log()[0].phase == "before_execute"


def test_bark_and_busy_errors_are_distinct_types():
    assert not issubclass(dogdb.DollyBarkError, dogdb.DollyBusyError)
    assert not issubclass(dogdb.DollyBusyError, dogdb.DollyBarkError)


def test_before_execute_priority_selects_bark_first():
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        faults={"BARK": 1, "GUARD_BOWL": 1, "IGNORE": 1, "SLOTH": 1},
        clock=lambda _: None,
    )
    with pytest.raises(dogdb.DollyBarkError):
        conn.execute("select id from t")
    assert [event.fault for event in conn.dolly.log()] == ["BARK"]


class _CountingAdapter:
    def __init__(self) -> None:
        self.executions = 0

    def execute(self, sql, params=None):
        self.executions += 1
        return LogicalResult(["id"], [(1,), (2,)], 2)

    @property
    def in_transaction(self):
        return False

    def close(self):
        pass


def test_no_drop_raises_only_after_backend_execution():
    conn = dogdb.wrap(_raw(), seed=42, faults={"NO_DROP": 1})
    adapter = _CountingAdapter()
    conn._adapter = adapter

    with pytest.raises(dogdb.DollyNoDropError) as caught:
        conn.execute("select id from t")

    assert adapter.executions == 1
    assert caught.value.outcome == "response_lost"
    assert caught.value.retryable is True
    event = conn.dolly.log()[0]
    assert event.phase == "on_result"
    assert event.outcome == "response_lost"


def test_no_drop_does_not_apply_to_writes():
    raw = _raw()
    conn = dogdb.wrap(raw, seed=42, faults={"NO_DROP": 1})
    conn.execute("insert into t values (4)")
    assert raw.execute("select count(*) from t").fetchone() == (4,)
    assert conn.dolly.log() == []
