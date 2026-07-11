from __future__ import annotations

import sqlite3
import uuid

import dogdb


def _database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    return raw


def _signature(events):
    return [
        (event.fault, event.decision_key, event.occurrence, event.outcome, event.details)
        for event in events
    ]


def test_same_inputs_produce_same_event_sequence():
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            _database(),
            seed=42,
            session_id="replay",
            faults={"SHUFFLE": 1},
        )
        conn.execute("select id from t").fetchall()
        runs.append(conn.dolly.log())
    assert runs[0] == runs[1]


def test_changing_uuid_params_does_not_change_default_decision():
    keys = []
    for value in (uuid.uuid4(), uuid.uuid4()):
        conn = dogdb.wrap(
            _database(), seed=42, session_id="uuid", faults={"SHUFFLE": 1}
        )
        conn.execute("select id from t where ? is not null", (value.hex,)).fetchall()
        keys.append(conn.dolly.log()[0].decision_key)
    assert keys[0] == keys[1]


def test_include_params_changes_decision_key():
    keys = []
    for value in ("alpha", "beta"):
        conn = dogdb.wrap(
            _database(),
            seed=42,
            session_id="faithful",
            include_params=True,
            faults={"SHUFFLE": 1},
        )
        conn.execute("select id from t where ? is not null", (value,)).fetchall()
        keys.append(conn.dolly.log()[0].decision_key)
    assert keys[0] != keys[1]


def test_occurrence_increments_per_template():
    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    for _ in range(3):
        conn.execute("select id from t").fetchall()
    assert [event.occurrence for event in conn.dolly.log()] == [1, 2, 3]


def test_seed_separates_decision_keys():
    keys = []
    for seed in (42, 43):
        conn = dogdb.wrap(
            _database(), seed=seed, session_id="seed-test", faults={"SHUFFLE": 1}
        )
        conn.execute("select id from t").fetchall()
        keys.append(conn.dolly.log()[0].decision_key)
    assert keys[0] != keys[1]
