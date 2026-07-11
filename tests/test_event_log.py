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


def test_stash_event_has_schema_v1_required_fields(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = _connection(path)
    conn.execute("select id from t").fetchall()
    line = json.loads(path.read_text().splitlines()[0])
    assert REQUIRED <= line.keys()
    assert line["schema_version"] == 1
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
