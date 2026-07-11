from __future__ import annotations

import sqlite3

import dogdb
import pytest

from dogdb.core.decision import DecisionEngine
from dogdb.core.sql import classify_sql


def _raw(rows: int = 20) -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(index,) for index in range(rows)])
    return raw


def test_echo_duplicates_derived_row_immediately_without_losing_rows():
    conn = dogdb.wrap(
        _raw(5), seed=42, session_id="echo-row", faults={"ECHO": 1}
    )
    rows = conn.execute("select id from t order by id").fetchall()
    event = conn.dolly.log()[0]
    expected_index = int.from_bytes(
        DecisionEngine.derive(event.decision_key, "rows:ECHO")[:8], "big"
    ) % 5

    assert len(rows) == 6
    assert rows[expected_index] == rows[expected_index + 1]
    assert {row for row in rows} == {(0,), (1,), (2,), (3,), (4,)}
    assert event.outcome == "rows_duplicated"
    assert event.details == {"row_index": expected_index}


def test_tail_chase_silent_returns_a_prefix_and_is_not_sticky():
    conn = dogdb.wrap(
        _raw(5), seed=42, faults={"TAIL_CHASE": 1}, tail_chase_mode="silent"
    )
    first = conn.execute("select id from t order by id").fetchall()
    second = conn.execute("select id from t order by id").fetchall()

    assert first == [(index,) for index in range(len(first))]
    assert second == [(index,) for index in range(len(second))]
    assert len(first) < 5 and len(second) < 5
    assert [event.occurrence for event in conn.dolly.log()] == [1, 2]
    assert conn.dolly.house() == []


def test_tail_chase_error_exposes_delivered_rows_and_logs_details():
    conn = dogdb.wrap(
        _raw(5), seed=42, faults={"TAIL_CHASE": 1}, tail_chase_mode="error"
    )
    with pytest.raises(dogdb.DollyTailChaseError) as caught:
        conn.execute("select id from t order by id")

    event = conn.dolly.log()[0]
    assert caught.value.outcome == "read_partial"
    assert caught.value.delivered_rows == event.details["delivered_rows"]
    assert event.outcome == "read_partial"
    assert event.details["delivered_rows"] + event.details["truncated_rows"] == 5
    assert conn.dolly.house() == []


def test_tail_chase_configuration_is_closed():
    with pytest.raises(ValueError, match="tail_chase_mode"):
        dogdb.wrap(_raw(), seed=42, tail_chase_mode="streaming")


def test_false_empty_preserves_columns_and_retry_can_recover():
    conn = dogdb.wrap(_raw(3), seed=42, faults={"FALSE_EMPTY": 1})
    first = conn.execute("select id from t order by id")
    assert first.description[0][0] == "id"
    assert first.fetchall() == []
    assert first.rowcount == 0

    conn._faults.policy.probabilities["FALSE_EMPTY"] = 0
    second = conn.execute("select id from t order by id").fetchall()

    assert second == [(0,), (1,), (2,)]
    assert [event.outcome for event in conn.dolly.log()] == ["empty_result"]
    assert conn.dolly.house() == []


@pytest.mark.parametrize(
    ("sql", "limit", "offset"),
    [
        ("select id from t limit 10 offset 10", 10, 10),
        ("select id from t limit 10", 10, None),
        ("select id from t limit ? offset ?", None, None),
        ("select id from t limit 5 + 5 offset 10", None, 10),
        ("select id from t limit 10 offset -1", 10, None),
        ("select * from (select id from t limit 1 offset 1) nested", None, None),
    ],
)
def test_classifier_detects_only_top_level_literal_limit_offset(
    sql: str, limit: int | None, offset: int | None
):
    classification = classify_sql(sql)
    assert classification.top_level_limit == limit
    assert classification.top_level_offset == offset


def test_page_hole_removes_one_or_more_rows_from_page_front():
    conn = dogdb.wrap(_raw(25), seed=42, faults={"PAGE_HOLE": 1})
    rows = conn.execute("select id from t order by id limit 10 offset 10").fetchall()
    event = conn.dolly.log()[0]
    removed = event.details["rows_removed"]

    assert 1 <= removed <= 10
    assert rows == [(index,) for index in range(10 + removed, 20)]
    assert event.outcome == "page_hole"
    assert conn.dolly.house() == []


def test_page_hole_is_ineligible_without_positive_literal_offset():
    conn = dogdb.wrap(_raw(10), seed=42, faults={"PAGE_HOLE": 1})
    rows = conn.execute("select id from t order by id limit 5").fetchall()
    assert rows == [(0,), (1,), (2,), (3,), (4,)]
    assert conn.dolly.log() == []


@pytest.mark.parametrize(
    ("fault", "options", "sql"),
    [
        ("ECHO", {}, "select id from t order by id"),
        ("TAIL_CHASE", {"tail_chase_mode": "silent"}, "select id from t order by id"),
        ("FALSE_EMPTY", {}, "select id from t order by id"),
        ("PAGE_HOLE", {}, "select id from t order by id limit 10 offset 10"),
    ],
)
def test_shape_faults_are_deterministic(fault: str, options: dict[str, str], sql: str):
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            _raw(25),
            seed=42,
            session_id=f"shape-{fault}",
            faults={fault: 1},
            **options,
        )
        rows = conn.execute(sql).fetchall()
        runs.append((rows, conn.dolly.log(), conn.dolly.house()))
    assert runs[0] == runs[1]
    assert runs[0][2] == []
