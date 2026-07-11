from __future__ import annotations

import sqlite3

import pytest

import dogdb
from dogdb import DogDBError, DollyIgnoredError, DollyStashedError


def _raw(rows: int = 5) -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(index,) for index in range(rows)])
    return raw


def test_stash_missing_removes_one_row_and_records_it():
    conn = dogdb.wrap(_raw(), seed=42, faults={"STASH": 1})
    result = conn.execute("select id from t").fetchall()
    treasure = conn.dolly.house()[0]
    assert len(result) == 4
    assert treasure.row not in result
    assert conn.dolly.log()[0].fault == "STASH"


def test_stash_error_has_story_and_machine_attributes():
    conn = dogdb.wrap(
        _raw(), seed=42, faults={"STASH": 1}, stash_mode="error"
    )
    with pytest.raises(DollyStashedError) as caught:
        conn.execute("select id from t")
    error = caught.value
    assert "Dolly took row #" in str(error)
    assert error.fault == "STASH"
    assert error.event_id
    assert error.outcome == "read_partial"


def test_shuffle_changes_order_but_not_row_set():
    conn = dogdb.wrap(_raw(), seed=42, faults={"SHUFFLE": 1})
    result = conn.execute("select id from t").fetchall()
    assert set(result) == {(0,), (1,), (2,), (3,), (4,)}
    assert result != [(0,), (1,), (2,), (3,), (4,)]


def test_shuffle_respects_top_level_order_by():
    conn = dogdb.wrap(_raw(), seed=42, faults={"SHUFFLE": 1})
    result = conn.execute("select id from t order by id").fetchall()
    assert result == [(0,), (1,), (2,), (3,), (4,)]
    assert conn.dolly.log() == []


def test_ignore_does_not_execute_and_retry_can_succeed():
    raw = _raw(0)
    conn = dogdb.wrap(raw, seed=42, faults={"IGNORE": 1})
    with pytest.raises(DollyIgnoredError) as caught:
        conn.execute("insert into t values (1)")
    assert caught.value.outcome == "not_executed"
    assert caught.value.retryable is True
    assert raw.execute("select count(*) from t").fetchone()[0] == 0
    conn._faults.policy.ignore = 0
    conn.execute("insert into t values (1)")
    assert raw.execute("select count(*) from t").fetchone()[0] == 1


def test_failure_injection_wins_and_only_one_fault_is_logged():
    conn = dogdb.wrap(
        _raw(), seed=42, faults={"IGNORE": 1, "SHUFFLE": 1}
    )
    with pytest.raises(DollyIgnoredError):
        conn.execute("select id from t")
    assert [event.fault for event in conn.dolly.log()] == ["IGNORE"]


def test_all_zero_probabilities_match_plain_connection():
    plain = _raw()
    expected = plain.execute("select id from t").fetchall()
    conn = dogdb.wrap(_raw(), seed=42, faults={"STASH": 0, "SHUFFLE": 0, "IGNORE": 0})
    assert conn.execute("select id from t").fetchall() == expected
    assert conn.dolly.log() == []


def test_backend_sql_error_is_not_wrapped():
    conn = dogdb.wrap(_raw(), seed=42)
    with pytest.raises(sqlite3.Error) as caught:
        conn.execute("select from")
    assert not isinstance(caught.value, DogDBError)


def test_shape_fault_precedes_value_fault_in_fixed_priority():
    conn = dogdb.wrap(_raw(), seed=42, faults={"ECHO": 1, "CHEW": 1})
    template, parameter, occurrence = conn._decisions.begin("select id from t", None)
    decision = conn._decisions.decide(
        template=template,
        parameter=parameter,
        occurrence=occurrence,
        phase="on_result",
    )

    selected = conn._faults.select_candidate(
        decision, {"CHEW", "ECHO"}, phase="on_result"
    )

    assert selected == "ECHO"


def test_all_declared_fault_names_are_accepted_before_their_opt_in_stages():
    names = {
        "BARK",
        "GUARD_BOWL",
        "IGNORE",
        "SLOTH",
        "NO_DROP",
        "STASH",
        "FALSE_EMPTY",
        "TAIL_CHASE",
        "PAGE_HOLE",
        "ECHO",
        "SHUFFLE",
        "TANGLED_LEASH",
        "CHEW",
        "WRONG_COUNT",
        "OLD_BONE",
    }
    conn = dogdb.wrap(_raw(), seed=42, faults={name: 0 for name in names})
    assert set(conn._faults.policy.probabilities) == names


def test_unknown_fault_name_is_rejected_before_wrapping():
    raw = _raw()
    with pytest.raises(ValueError, match=r"unknown faults: ZOOMIES"):
        dogdb.wrap(raw, seed=42, faults={"ZOOMIES": 1})
    assert raw.execute("select count(*) from t").fetchone() == (5,)
