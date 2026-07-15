from __future__ import annotations

import dogdb
import pytest

from conftest import raw_three_row_connection

from dogdb.core.decision import DecisionEngine
from dogdb.core.house import rebuild_house

def test_auto_return_runs_before_mood_and_current_fault():
    conn = dogdb.wrap(
        raw_three_row_connection(),
        seed=42,
        session_id="auto-order-v4-0",
        faults={"STASH": 1, "ECHO": 1},
        auto_return=(1, 1),
        mood={"epoch_length": 1},
    )
    conn.execute("select id from t order by id").fetchall()
    assert len(conn.dolly.house()) == 1

    rows = conn.execute("select id from t order by id").fetchall()
    events = conn.dolly.log()
    returned = next(event for event in events if event.phase == "auto_return")
    mood_at_tick_two = next(
        event
        for event in events
        if event.event_type == "mood_changed" and event.details["tick"] == 2
    )
    echo = next(event for event in events if event.fault == "ECHO")

    assert len(rows) == 4
    assert returned.seq < mood_at_tick_two.seq < echo.seq
    stash = next(event for event in events if event.fault == "STASH")
    assert returned.event_id == DecisionEngine.deterministic_id(
        stash.decision_key, f"event:{returned.seq}:RETURN"
    )
    assert conn.dolly.house() == []


def test_auto_return_timing_is_deterministic():
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            raw_three_row_connection(),
            seed=42,
            session_id="auto-replay",
            faults={"STASH": 1},
            auto_return=(2, 4),
        )
        for _ in range(8):
            conn.execute("select id from t order by id").fetchall()
        runs.append((conn.dolly.log(), conn.dolly.house()))
    assert runs[0] == runs[1]
    assert any(event.phase == "auto_return" for event in runs[0][0])


def test_hold_period_uses_standard_return_tag_within_configured_range():
    conn = dogdb.wrap(
        raw_three_row_connection(), seed=42, faults={"STASH": 1}, auto_return=(2, 4)
    )
    conn.execute("select id from t order by id").fetchall()
    treasure = conn.dolly.house()[0]
    stash = conn.dolly.log()[0]
    expected_hold = 2 + int.from_bytes(
        DecisionEngine.derive(stash.decision_key, "hold:RETURN")[:8], "big"
    ) % 3
    due_tick, _ = conn._auto_return._scheduled[treasure.treasure_id]

    assert due_tick == 1 + expected_hold


def test_executemany_operation_can_trigger_auto_return():
    conn = dogdb.wrap(
        raw_three_row_connection(), seed=42, faults={"STASH": 1}, auto_return=(1, 1)
    )
    conn.execute("select id from t order by id").fetchall()
    conn.executemany("insert into t values (?)", [(4,), (5,)])

    assert conn.dolly.house() == []
    assert conn.dolly.log()[-1].phase == "auto_return"


def test_unsupported_parameter_passthrough_can_trigger_auto_return():
    class ConformingString(str):
        def __conform__(self, protocol):
            return str(self)

    conn = dogdb.wrap(
        raw_three_row_connection(), seed=42, faults={"STASH": 1}, auto_return=(1, 1)
    )
    conn.execute("select id from t order by id").fetchall()

    assert conn.execute("select ?", (ConformingString("bone"),)).fetchall() == [
        ("bone",)
    ]
    assert conn.dolly.house() == []
    assert conn.dolly.log()[-1].phase == "auto_return"
    assert conn._logical_tick == 2


def test_manual_return_cancels_scheduled_auto_return():
    conn = dogdb.wrap(
        raw_three_row_connection(), seed=42, faults={"STASH": 1}, auto_return=(2, 2)
    )
    conn.execute("select id from t order by id").fetchall()
    treasure_id = conn.dolly.house()[0].treasure_id
    conn.dolly.return_treasure(treasure_id)
    conn.execute("pragma user_version").fetchall()
    conn.execute("pragma user_version").fetchall()

    returned = [
        event for event in conn.dolly.log() if event.event_type == "treasure_returned"
    ]
    assert [event.phase for event in returned] == ["manual_return"]


def test_house_projection_includes_auto_return_events():
    conn = dogdb.wrap(
        raw_three_row_connection(), seed=42, faults={"STASH": 1}, auto_return=(1, 1)
    )
    conn.execute("select id from t order by id").fetchall()
    conn.execute("pragma user_version").fetchall()

    assert rebuild_house(conn.dolly.log()) == []
    assert conn.dolly.house() == []


@pytest.mark.parametrize(
    "setting",
    [
        (0, 1),
        (3, 2),
        (1,),
        {"enabled": "yes"},
        {"unknown": 1},
    ],
)
def test_invalid_auto_return_settings_are_rejected(setting):
    with pytest.raises(ValueError, match="auto_return"):
        dogdb.wrap(raw_three_row_connection(), seed=42, auto_return=setting)


def test_auto_return_disabled_has_no_logical_clock():
    conn = dogdb.wrap(raw_three_row_connection(), seed=42)
    assert conn._auto_return is None
    assert conn._logical_tick is None
