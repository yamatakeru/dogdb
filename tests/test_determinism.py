from __future__ import annotations

import datetime
import hashlib
import itertools
import sqlite3
import uuid
from decimal import Decimal

import dogdb
import pytest

from dogdb.core.decision import DecisionEngine
from dogdb.core.fingerprints import (
    parameter_fingerprint,
    params_in_fingerprint_domain,
)


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


def test_unsupported_parameter_passthrough_does_not_consume_occurrence():
    class ConformingString(str):
        def __conform__(self, protocol):
            return str(self)

    runs = []
    for include_passthrough in (False, True):
        conn = dogdb.wrap(
            _database(),
            seed=42,
            session_id="passthrough-occurrence",
            faults={"SHUFFLE": 1},
        )
        conn.execute("select id from t").fetchall()
        if include_passthrough:
            conn.execute("select ?", (ConformingString("bone"),)).fetchall()
        conn.execute("select id from t").fetchall()
        runs.append(conn.dolly.log())

    assert [event.occurrence for event in runs[1]] == [1, 2]
    assert [event.decision_key for event in runs[1]] == [
        event.decision_key for event in runs[0]
    ]


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


def test_unsupported_parameter_type_preserves_backend_error_without_event():
    class UnstableParameter:
        pass

    sql = "select id from t where ? is not null"
    raw = _database()
    with pytest.raises(sqlite3.ProgrammingError) as raw_error:
        raw.execute(sql, (UnstableParameter(),))

    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    with pytest.raises(sqlite3.ProgrammingError) as wrapped_error:
        conn.execute(sql, (UnstableParameter(),))

    assert str(wrapped_error.value) == str(raw_error.value)
    assert conn.dolly.log() == []
    assert conn.dolly.stats()["passthrough"] == {
        "unsupported_parameter_type": 1
    }


def test_stable_non_json_parameters_have_deterministic_fingerprint():
    params = (
        datetime.datetime(2026, 7, 11, 12, 34, 56),
        Decimal("123.450"),
        uuid.UUID("12345678-1234-5678-1234-567812345678"),
        b"\x00\xff",
    )
    key = b"fixed-key"

    assert parameter_fingerprint(params, key) == parameter_fingerprint(params, key)


def test_every_parameter_sequence_in_domain_can_be_fingerprinted():
    values = (
        None,
        False,
        0,
        1.5,
        "treat",
        b"\x00\xff",
        bytearray(b"bone"),
        datetime.date(2026, 7, 12),
        datetime.time(12, 34, 56),
        datetime.datetime(2026, 7, 12, 12, 34, 56),
        Decimal("123.450"),
        uuid.UUID("12345678-1234-5678-1234-567812345678"),
    )

    for length in range(4):
        for params in itertools.product(values, repeat=length):
            assert params_in_fingerprint_domain(params)
            assert parameter_fingerprint(params, b"property-test-key").startswith(
                "hmac-sha256:"
            )


def test_parameter_domain_uses_strict_type_matching():
    class StringSubclass(str):
        pass

    params = ("supported", StringSubclass("treat"))
    assert not params_in_fingerprint_domain(params)
    with pytest.raises(TypeError, match="StringSubclass"):
        parameter_fingerprint(params, b"strict-type-key")


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
