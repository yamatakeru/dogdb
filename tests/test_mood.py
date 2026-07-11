from __future__ import annotations

import json
import sqlite3

import dogdb
import pytest

from dogdb.core.mood import MoodEngine, parse_mood_config


def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    return raw


def test_logical_clock_counts_passthrough_execute_and_executemany():
    conn = dogdb.wrap(_raw(), seed=42, mood={"epoch_length": 100})
    for _ in range(3):
        conn.execute("pragma user_version").fetchall()
    conn.execute("select id from t").fetchall()

    assert conn._mood.tick == 4

    conn.executemany("insert into t values (?)", [(4,), (5,)])
    assert conn._mood.tick == 5


def test_mood_changes_only_at_epoch_boundaries():
    conn = dogdb.wrap(
        _raw(), seed=42, session_id="mood-boundary", mood={"epoch_length": 2}
    )
    for _ in range(8):
        conn.execute("select id from t").fetchall()

    mood_events = [
        event for event in conn.dolly.log() if event.event_type == "mood_changed"
    ]
    assert mood_events
    assert all(event.details["tick"] % 2 == 0 for event in mood_events)
    assert all(
        event.details["from"] != event.details["to"] for event in mood_events
    )
    assert conn._mood.tick == 8


def test_mood_event_file_contains_only_core_fields_and_details(tmp_path):
    path = tmp_path / "mood.jsonl"
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="mood-boundary",
        mood={"epoch_length": 2},
        log_path=path,
    )
    for _ in range(4):
        conn.execute("select id from t").fetchall()

    lines = [json.loads(line) for line in path.read_text().splitlines()]
    event = next(item for item in lines if item["event_type"] == "mood_changed")
    assert set(event) == {
        "schema_version",
        "event_id",
        "session_id",
        "seq",
        "event_type",
        "details",
    }
    assert set(event["details"]) == {"from", "to", "tick"}


def test_default_mood_multiplier_table_matches_design():
    config = parse_mood_config(True)
    assert config is not None
    engine = MoodEngine(seed=42, session_id="coefficients", config=config)

    assert all(engine.multiplier(fault) == 1.0 for fault in ("IGNORE", "ECHO"))
    engine.state = "SLEEPY"
    assert engine.multiplier("IGNORE") == 3.0
    assert engine.multiplier("SLOTH") == 3.0
    assert engine.multiplier("NO_DROP") == 3.0
    assert engine.multiplier("GUARD_BOWL") == 3.0
    assert engine.multiplier("SHUFFLE") == 0.5
    assert engine.multiplier("ECHO") == 0.5
    assert engine.multiplier("TAIL_CHASE") == 0.5
    engine.state = "ZOOMY"
    assert engine.multiplier("SHUFFLE") == 3.0
    assert engine.multiplier("ECHO") == 3.0
    assert engine.multiplier("TAIL_CHASE") == 3.0
    assert engine.multiplier("CHEW") == 3.0
    assert engine.multiplier("IGNORE") == 0.5
    assert engine.multiplier("SLOTH") == 0.5


def test_mood_multiplier_overrides_deep_merge_with_defaults():
    config = parse_mood_config(
        {"multipliers": {"sleepy": {"echo": 2.0}, "calm": {"bark": 0.0}}}
    )
    assert config is not None
    assert config.multipliers["SLEEPY"]["ECHO"] == 2.0
    assert config.multipliers["SLEEPY"]["IGNORE"] == 3.0
    assert config.multipliers["CALM"]["BARK"] == 0.0


@pytest.mark.parametrize(
    "mood",
    [
        "enabled",
        {"epoch_length": 0},
        {"enabled": "yes"},
        {"unknown": 1},
        {"multipliers": {"HUNGRY": {"ECHO": 1}}},
        {"multipliers": {"CALM": {"ZOOMIES": 1}}},
        {"multipliers": {"CALM": {"ECHO": -1}}},
    ],
)
def test_invalid_mood_settings_are_rejected(mood):
    with pytest.raises(ValueError, match="mood|fault"):
        dogdb.wrap(_raw(), seed=42, mood=mood)


def test_calm_mood_does_not_change_fault_decision_key_or_event():
    plain = dogdb.wrap(
        _raw(), seed=42, session_id="calm-compatible", faults={"ECHO": 1}
    )
    enabled = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="calm-compatible",
        faults={"ECHO": 1},
        mood={"epoch_length": 100},
    )

    assert plain.execute("select id from t order by id").fetchall() == enabled.execute(
        "select id from t order by id"
    ).fetchall()
    assert plain.dolly.log() == enabled.dolly.log()


def test_mood_changes_weight_only_and_not_decision_key():
    plain = dogdb.wrap(
        _raw(), seed=42, session_id="weight-only", faults={"ECHO": 1}
    )
    plain.execute("select id from t order by id").fetchall()
    expected_key = plain.dolly.log()[0].decision_key

    suppressed = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="weight-only",
        faults={"ECHO": 1},
        mood={
            "epoch_length": 100,
            "multipliers": {"CALM": {"ECHO": 0.0}},
        },
        debug=True,
    )
    suppressed.execute("select id from t order by id").fetchall()
    on_result = next(
        event for event in suppressed.dolly.log() if event.phase == "on_result"
    )

    assert on_result.event_type == "decision_evaluated"
    assert on_result.decision_key == expected_key


def test_sleepy_multiplier_changes_only_fire_threshold():
    conn = dogdb.wrap(
        _raw(), seed=42, session_id="sleepy-threshold", mood=True
    )
    template, parameter, occurrence = conn._decisions.begin(
        "select id from t", None
    )
    decision = conn._decisions.decide(
        template=template,
        parameter=parameter,
        occurrence=occurrence,
        phase="before_execute",
    )
    threshold = conn._decisions.legacy_unit_interval(
        decision.decision_key, "IGNORE"
    )
    conn._faults.policy.probabilities["IGNORE"] = threshold / 2

    conn._mood.state = "SLEEPY"
    assert conn._faults._fires(decision, "IGNORE") is True
    conn._faults.mood = None
    assert conn._faults._fires(decision, "IGNORE") is False
    assert decision.decision_key == conn._decisions.decide(
        template=template,
        parameter=parameter,
        occurrence=occurrence,
        phase="before_execute",
    ).decision_key


def test_mood_enabled_runs_are_fully_deterministic():
    runs = []
    for _ in range(2):
        sleeps: list[float] = []
        conn = dogdb.wrap(
            _raw(),
            seed=42,
            session_id="mood-replay",
            faults={"SLOTH": 0.35, "ECHO": 0.35},
            mood={"epoch_length": 2},
            clock=sleeps.append,
        )
        rows = [
            conn.execute("select id from t order by id").fetchall()
            for _ in range(12)
        ]
        runs.append((rows, sleeps, conn.dolly.log()))
    assert runs[0] == runs[1]
    assert any(event.event_type == "mood_changed" for event in runs[0][2])


def test_partial_replay_is_not_guaranteed_to_match_session_tail():
    full = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="partial-replay",
        faults={"ECHO": 1},
        mood={"epoch_length": 2},
    )
    for _ in range(20):
        full.execute("select id from t order by id").fetchall()
    full_tail = full.dolly.log()[-10:]

    partial = dogdb.wrap(
        _raw(),
        seed=42,
        session_id="partial-replay",
        faults={"ECHO": 1},
        mood={"epoch_length": 2},
    )
    for _ in range(10):
        partial.execute("select id from t order by id").fetchall()

    assert full_tail != partial.dolly.log()


def test_mood_disabled_has_no_clock_or_mood_events():
    conn = dogdb.wrap(_raw(), seed=42, faults={"ECHO": 1})
    conn.execute("select id from t order by id").fetchall()
    assert conn._mood is None
    assert all(event.event_type != "mood_changed" for event in conn.dolly.log())
