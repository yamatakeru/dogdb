from __future__ import annotations

import json
import sqlite3

import pytest

import dogdb
from dogdb.core.event_log import Event
from dogdb.core.faults import (
    FAULT_TAXONOMY,
    KNOWN_FAULTS,
    ROWCOUNT_VISIBLE_FAULTS,
)


EXPECTED_TAXONOMY = {
    ("BARK", None): ("failure_injection", "error", False),
    ("GUARD_BOWL", None): ("failure_injection", "error", False),
    ("IGNORE", None): ("failure_injection", "error", False),
    ("SLOTH", None): ("temporal", "delay", False),
    ("NO_DROP", None): ("failure_injection", "error", False),
    ("STASH", "error"): ("shape", "error", False),
    ("STASH", "missing"): ("shape", "silent_corruption", False),
    ("FALSE_EMPTY", None): ("shape", "silent_corruption", True),
    ("TAIL_CHASE", "error"): ("shape", "error", True),
    ("TAIL_CHASE", "silent"): ("shape", "silent_corruption", True),
    ("PAGE_HOLE", None): ("shape", "silent_corruption", True),
    ("ECHO", None): ("shape", "silent_corruption", True),
    ("SHUFFLE", None): ("shape", "silent_corruption", False),
    ("TANGLED_LEASH", None): ("value", "silent_corruption", False),
    ("CHEW", None): ("value", "silent_corruption", False),
    ("WRONG_COUNT", None): ("value", "silent_corruption", True),
    ("OLD_BONE", None): ("state", "silent_corruption", False),
}


def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, value text)")
    raw.executemany(
        "insert into t values (?, ?)",
        [(1, "alpha"), (2, "beta"), (3, "gamma")],
    )
    return raw


def test_taxonomy_is_complete_and_matches_the_closed_contract():
    actual = {
        key: (value.category, value.severity, value.rowcount_visible)
        for key, value in FAULT_TAXONOMY.items()
    }

    assert actual == EXPECTED_TAXONOMY
    assert {fault for fault, _mode in FAULT_TAXONOMY} == KNOWN_FAULTS
    assert {mode for fault, mode in FAULT_TAXONOMY if fault == "STASH"} == {
        "error",
        "missing",
    }
    assert {
        mode for fault, mode in FAULT_TAXONOMY if fault == "TAIL_CHASE"
    } == {"error", "silent"}


def test_rowcount_visible_faults_preserve_the_existing_membership():
    assert ROWCOUNT_VISIBLE_FAULTS == {
        "FALSE_EMPTY",
        "TAIL_CHASE",
        "ECHO",
        "PAGE_HOLE",
        "WRONG_COUNT",
    }


def test_bark_error_exposes_read_only_taxonomy_properties():
    conn = dogdb.wrap(_raw(), seed=42, faults={"BARK": 1})

    with pytest.raises(dogdb.DollyBarkError) as caught:
        conn.execute("select id from t")

    assert caught.value.category == "failure_injection"
    assert caught.value.severity == "error"
    with pytest.raises(AttributeError):
        caught.value.category = "shape"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        caught.value.severity = "delay"  # type: ignore[misc]


def test_limit_error_has_no_fault_taxonomy():
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        max_intervention_rows=2,
        on_max_rows="error",
    )

    with pytest.raises(dogdb.DollyLimitError) as caught:
        conn.execute("select id from t").fetchall()

    assert caught.value.category is None
    assert caught.value.severity is None


@pytest.mark.parametrize(
    ("fault", "sql", "category"),
    [
        ("CHEW", "select value from t where id = 1", "value"),
        ("SHUFFLE", "select id from t", "shape"),
    ],
)
def test_silent_fault_events_include_taxonomy(fault, sql, category, tmp_path):
    path = tmp_path / "events.jsonl"
    conn = dogdb.wrap(_raw(), seed=42, faults={fault: 1}, log_path=path)

    conn.execute(sql).fetchall()
    event = conn.dolly.log()[0]

    assert event.event_type == "fault_injected"
    assert event.category == category
    assert event.severity == "silent_corruption"
    assert event.schema_version == 2
    line = json.loads(path.read_text().splitlines()[0])
    assert line["category"] == category
    assert line["severity"] == "silent_corruption"


@pytest.mark.parametrize(
    ("mode", "severity", "raises"),
    [
        ("missing", "silent_corruption", False),
        ("error", "error", True),
    ],
)
def test_stash_taxonomy_uses_the_firing_mode(mode, severity, raises):
    conn = dogdb.wrap(_raw(), seed=42, faults={"STASH": 1}, stash_mode=mode)

    if raises:
        with pytest.raises(dogdb.DollyStashedError) as caught:
            conn.execute("select id from t")
        assert caught.value.category == "shape"
        assert caught.value.severity == severity
    else:
        conn.execute("select id from t").fetchall()

    event = conn.dolly.log()[0]
    assert event.category == "shape"
    assert event.severity == severity


def test_treasure_returned_event_does_not_include_taxonomy(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = dogdb.wrap(_raw(), seed=42, faults={"STASH": 1}, log_path=path)
    conn.execute("select id from t").fetchall()

    conn.dolly.return_all()

    returned = conn.dolly.log()[-1]
    assert returned.event_type == "treasure_returned"
    assert returned.category is None
    assert returned.severity is None
    returned_line = json.loads(path.read_text().splitlines()[-1])
    assert "category" not in returned_line
    assert "severity" not in returned_line


def test_taxonomy_fields_are_excluded_from_replay_comparison():
    existing_v2 = {
        "schema_version": 2,
        "event_id": "event-1",
        "session_id": "replay",
        "seq": 1,
        "event_type": "fault_injected",
        "fault": "SHUFFLE",
        "phase": "on_result",
        "template_fingerprint": "sha256:template",
        "parameter_fingerprint": "hmac-sha256:parameter",
        "occurrence": 1,
        "decision_key": "sha256:decision",
        "outcome": "rows_reordered",
        "details": {},
    }

    legacy = Event.from_dict(existing_v2)
    classified = Event.from_dict(
        {
            **existing_v2,
            "category": "shape",
            "severity": "silent_corruption",
        }
    )

    assert legacy == classified
    assert legacy.category is None
    assert classified.category == "shape"
