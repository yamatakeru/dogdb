from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

import pytest

import dogdb
from dogdb.core.event_log import read_events


REQUIRED = {
    "schema_version",
    "event_id",
    "session_id",
    "seq",
    "event_type",
    "fault",
    "phase",
    "template_fingerprint",
    "parameter_fingerprint",
    "occurrence",
    "decision_key",
    "outcome",
    "details",
}


def _connection(path=None):
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, secret text)")
    raw.executemany("insert into t values (?, ?)", [(1, "a"), (2, "b"), (3, "c")])
    return dogdb.wrap(raw, seed=42, faults={"STASH": 1}, log_path=path)


def test_stash_event_has_schema_v2_and_v1_compatible_fields(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = _connection(path)
    conn.execute("select id from t").fetchall()
    line = json.loads(path.read_text().splitlines()[0])
    assert REQUIRED <= line.keys()
    assert line["schema_version"] == 2
    assert line["details"]["row_indices"]


def test_secret_parameter_and_rows_are_not_logged(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = _connection(path)
    secret = "top-secret-raw-value"
    conn.execute("select id from t where ? is not null", (secret,)).fetchall()
    contents = path.read_text()
    assert secret not in contents
    assert "select id" not in contents.lower()
    for treasure in conn.dolly.house():
        assert repr(treasure.row) not in contents


def test_sequence_is_contiguous():
    conn = _connection()
    conn._faults.policy.stash = 0
    conn._faults.policy.shuffle = 1
    for sql in ("select id from t", "select secret from t", "select id, secret from t"):
        conn.execute(sql).fetchall()
    assert [event.seq for event in conn.dolly.log()] == [1, 2, 3]


def test_log_api_returns_attribute_objects():
    conn = _connection()
    conn.execute("select id from t").fetchall()
    assert conn.dolly.log()[-1].fault == "STASH"


def test_corrupt_json_line_is_skipped_with_warning(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = _connection(path)
    conn.execute("select id from t").fetchall()
    with path.open("a") as stream:
        stream.write('{"schema_version": 1\n')
    with pytest.warns(RuntimeWarning, match="corrupt DogDB event"):
        events = read_events(path)
    assert len(events) == 1
    assert REQUIRED == set(asdict(events[0]))


def test_invalid_utf8_line_is_skipped_with_warning(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = _connection(path)
    conn.execute("select id from t").fetchall()
    conn.execute("select secret from t").fetchall()
    expected_fingerprints = [
        event.template_fingerprint for event in conn.dolly.log()
    ]
    valid_lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(valid_lines[0] + b"\xff\xfe corrupt\n" + valid_lines[1])

    with pytest.warns(RuntimeWarning, match="corrupt DogDB event"):
        events = read_events(path)

    assert len(events) == 2
    assert [event.template_fingerprint for event in events] == expected_fingerprints


def test_v1_fixture_and_v2_append_are_read_together(tmp_path):
    path = tmp_path / "mixed.jsonl"
    fixture = {
        "schema_version": 1,
        "event_id": "legacy-event",
        "session_id": "legacy-session",
        "seq": 1,
        "event_type": "fault_injected",
        "fault": "IGNORE",
        "phase": "before_execute",
        "template_fingerprint": "sha256:legacy-template",
        "parameter_fingerprint": "hmac-sha256:legacy-parameter",
        "occurrence": 1,
        "decision_key": "sha256:legacy-decision",
        "outcome": "not_executed",
        "details": {},
    }
    path.write_text(json.dumps(fixture) + "\n")
    conn = _connection(path)
    conn.execute("select id from t").fetchall()

    events = read_events(path)

    assert [event.schema_version for event in events] == [1, 2]
    assert [event.session_id for event in events] == [
        "legacy-session",
        conn._events.session_id,
    ]


def test_unknown_schema_version_is_skipped_with_warning(tmp_path):
    path = tmp_path / "unknown-version.jsonl"
    valid = {
        "schema_version": 1,
        "event_id": "legacy-event",
        "session_id": "legacy-session",
        "seq": 1,
        "event_type": "fault_injected",
        "fault": "IGNORE",
        "phase": "before_execute",
        "template_fingerprint": "sha256:legacy-template",
        "parameter_fingerprint": "hmac-sha256:legacy-parameter",
        "occurrence": 1,
        "decision_key": "sha256:legacy-decision",
        "outcome": "not_executed",
        "details": {},
    }
    unknown = {**valid, "schema_version": 99, "event_id": "future-event"}
    path.write_text(json.dumps(valid) + "\n" + json.dumps(unknown) + "\n")

    with pytest.warns(RuntimeWarning, match=r"unsupported schema_version 99"):
        events = read_events(path)

    assert [event.event_id for event in events] == ["legacy-event"]


def test_invalid_required_field_types_are_skipped_without_losing_valid_rows(
    tmp_path,
):
    path = tmp_path / "invalid-types.jsonl"
    valid = {
        "schema_version": 2,
        "event_id": "valid-event",
        "session_id": "session",
        "seq": 1,
        "event_type": "mood_changed",
        "details": {"from": "CALM", "to": "SLEEPY", "tick": 10},
    }
    invalid = [
        {**valid, "schema_version": True, "event_id": "bool-version"},
        {**valid, "event_id": None, "seq": 2},
        {**valid, "event_id": "string-seq", "seq": "3"},
    ]
    final = {**valid, "event_id": "final-event", "seq": 4}
    path.write_text(
        "\n".join(json.dumps(event) for event in [valid, *invalid, final]) + "\n"
    )

    with pytest.warns(RuntimeWarning, match="corrupt DogDB event") as warnings:
        events = read_events(path)

    assert len(warnings) == 3
    assert [event.event_id for event in events] == ["valid-event", "final-event"]


def test_schema_v2_mood_event_does_not_require_fingerprint_fields(tmp_path):
    path = tmp_path / "mood.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "event_id": "mood-1",
                "session_id": "mood-session",
                "seq": 1,
                "event_type": "mood_changed",
                "details": {"from": "CALM", "to": "ZOOMY", "tick": 10},
            }
        )
        + "\n"
    )

    event = read_events(path)[0]

    assert event.event_type == "mood_changed"
    assert event.template_fingerprint is None
    assert event.details == {"from": "CALM", "to": "ZOOMY", "tick": 10}


def test_non_object_json_line_is_skipped_with_warning(tmp_path):
    path = tmp_path / "array.jsonl"
    path.write_text("[]\n")
    with pytest.warns(RuntimeWarning, match="event must be a JSON object"):
        assert read_events(path) == []


def test_limit_exceeded_event_records_metadata_without_rows(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = dogdb.wrap(
        sqlite3.connect(":memory:"),
        seed=42,
        faults={"STASH": 1},
        max_intervention_rows=2,
        log_path=path,
    )
    conn._connection.execute("create table t(id integer, secret text)")
    secret = "never-log-this-row-value"
    conn._connection.executemany(
        "insert into t values (?, ?)", [(1, secret), (2, secret), (3, secret)]
    )

    rows = conn.execute("select id, secret from t").fetchall()
    event = conn.dolly.log()[0]

    assert len(rows) == 3
    assert event.event_type == "limit_exceeded"
    assert event.outcome == "fault_skipped"
    assert event.details == {
        "limit": "max_intervention_rows",
        "configured": 2,
        "observed": 3,
    }
    assert secret not in path.read_text()


@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
def test_limit_error_is_logged_before_it_is_raised(backend):
    if backend == "sqlite":
        raw = sqlite3.connect(":memory:")
    else:
        import duckdb

        raw = duckdb.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    conn = dogdb.wrap(
        raw,
        seed=42,
        max_intervention_rows=2,
        on_max_rows="error",
    )

    with pytest.raises(dogdb.DollyLimitError) as caught:
        conn.execute("select id from t").fetchall()

    event = conn.dolly.log()[-1]
    assert event.event_type == "limit_exceeded"
    assert event.outcome == "error"
    assert caught.value.event_id == event.event_id
    assert caught.value.fault is None
    assert caught.value.retryable is False
    assert "max_intervention_rows" in str(caught.value)


def test_on_max_rows_rejects_unknown_mode():
    with pytest.raises(ValueError, match="on_max_rows"):
        dogdb.wrap(
            sqlite3.connect(":memory:"),
            seed=42,
            on_max_rows="truncate",
        )


def test_event_log_alias_is_not_accepted():
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        dogdb.wrap(
            sqlite3.connect(":memory:"),
            seed=42,
            **{"event_log": "events.jsonl"},
        )


def test_debug_records_non_firing_decisions_only_when_enabled():
    quiet = dogdb.wrap(sqlite3.connect(":memory:"), seed=42)
    quiet.execute("select 1 union all select 2").fetchall()
    assert quiet.dolly.log() == []

    debug = dogdb.wrap(sqlite3.connect(":memory:"), seed=42, debug=True)
    debug.execute("select 1 union all select 2").fetchall()

    events = debug.dolly.log()
    assert [event.event_type for event in events] == [
        "decision_evaluated",
        "decision_evaluated",
    ]
    assert all(event.outcome == "not_injected" for event in events)
    assert events[0].details == {
        "faults": ["BARK", "GUARD_BOWL", "IGNORE", "SLOTH"]
    }
