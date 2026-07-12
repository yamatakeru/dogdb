from __future__ import annotations

import datetime
import hashlib
import sqlite3
import uuid
from decimal import Decimal

import dogdb
import pytest

from dogdb.core.fingerprints import parameter_fingerprint
from dogdb.core.decision import DecisionEngine


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


def test_occurrence_is_not_evicted_after_many_distinct_templates():
    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    first_sql = "select 0 union all select 1"

    conn.execute(first_sql).fetchall()
    for value in range(2, 10_002):
        conn.execute(f"select {value}").fetchall()
    conn.execute(first_sql).fetchall()

    assert [event.occurrence for event in conn.dolly.log()] == [1, 2]


def test_seed_separates_decision_keys():
    keys = []
    for seed in (42, 43):
        conn = dogdb.wrap(
            _database(), seed=seed, session_id="seed-test", faults={"SHUFFLE": 1}
        )
        conn.execute("select id from t").fetchall()
        keys.append(conn.dolly.log()[0].decision_key)
    assert keys[0] != keys[1]


def test_unstable_parameter_type_is_rejected_without_event():
    class UnstableParameter:
        pass

    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})

    with pytest.raises(TypeError, match=r"UnstableParameter.*stable canonical text"):
        conn.execute("select id from t where ? is not null", (UnstableParameter(),))

    assert conn.dolly.log() == []


def test_stable_non_json_parameters_have_deterministic_fingerprint():
    params = (
        datetime.datetime(2026, 7, 11, 12, 34, 56),
        Decimal("123.450"),
        uuid.UUID("12345678-1234-5678-1234-567812345678"),
        b"\x00\xff",
    )
    key = b"fixed-key"

    assert parameter_fingerprint(params, key) == parameter_fingerprint(params, key)


def test_v2_derivation_uses_colon_separated_purpose_tags():
    decision_key = "sha256:fixed"
    tag = "fire:ECHO"
    assert DecisionEngine.derive(decision_key, tag) == hashlib.sha256(
        f"{decision_key}:{tag}".encode()
    ).digest()


def test_fault_fire_tags_are_domain_separated():
    keys = [f"sha256:{index:064x}" for index in range(64)]
    echo = [DecisionEngine.unit_interval(key, "fire:ECHO") < 0.5 for key in keys]
    chew = [DecisionEngine.unit_interval(key, "fire:CHEW") < 0.5 for key in keys]
    assert echo != chew
    assert any(left != right for left, right in zip(echo, chew, strict=True))
