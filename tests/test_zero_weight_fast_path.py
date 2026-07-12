from __future__ import annotations

import sqlite3

import dogdb
from dogdb.core.fingerprints import parameter_fingerprint, template_fingerprint


def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, value text)")
    raw.executemany("insert into t values (?, ?)", [(1, "a"), (2, "b")])
    return raw


def test_runtime_weight_change_preserves_third_decision_identity():
    sql = "select id from t order by id"
    delayed = dogdb.wrap(
        _raw(), seed=42, session_id="runtime-weight", faults={"ECHO": 0}
    )
    delayed.execute(sql).fetchall()
    delayed.execute(sql).fetchall()
    delayed._faults.policy.probabilities["ECHO"] = 1
    delayed_rows = delayed.execute(sql).fetchall()
    delayed_event = delayed.dolly.log()[0]

    enabled = dogdb.wrap(
        _raw(), seed=42, session_id="runtime-weight", faults={"ECHO": 1}
    )
    for _ in range(2):
        enabled.execute(sql).fetchall()
    enabled_rows = enabled.execute(sql).fetchall()
    enabled_event = enabled.dolly.log()[-1]

    assert delayed_event.occurrence == enabled_event.occurrence == 3
    assert delayed_event.decision_key == enabled_event.decision_key
    assert delayed_event.fault == enabled_event.fault == "ECHO"
    assert delayed_rows == enabled_rows


def test_debug_records_zero_weight_decisions_with_fingerprints():
    conn = dogdb.wrap(_raw(), seed=42, faults={}, debug=True)

    conn.execute("select id from t order by id").fetchall()

    events = conn.dolly.log()
    assert [event.event_type for event in events] == [
        "decision_evaluated",
        "decision_evaluated",
    ]
    assert [event.phase for event in events] == ["before_execute", "on_result"]
    assert all(event.decision_key for event in events)
    assert all(event.parameter_fingerprint for event in events)


def test_include_params_and_old_bone_paths_preserve_fingerprints_and_cache():
    sql = "select value from t where id = ?"
    params = (1,)
    included = dogdb.wrap(
        _raw(), seed=42, include_params=True, faults={"ECHO": 1}
    )
    included.execute(sql, params).fetchall()
    event = included.dolly.log()[0]
    assert event.parameter_fingerprint == parameter_fingerprint(
        params, included._decisions._hmac_key
    )

    stale = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
    first = stale.execute(sql, params).fetchall()
    second = stale.execute(sql, params).fetchall()
    assert second == first
    assert stale.dolly.log()[0].fault == "OLD_BONE"
    assert [entry.occurrence for entry in stale._stale_cache.entries()] == [1, 2]


def test_all_zero_weights_preserve_classification_stats():
    conn = dogdb.wrap(_raw(), seed=42, faults={})
    sql = "select id from t order by id"

    for _ in range(3):
        conn.execute(sql).fetchall()

    assert conn.dolly.log() == []
    assert conn.dolly.stats()["fingerprints"][template_fingerprint(sql)] == {
        "select": 3,
        "unknown": 0,
        "interventions": 0,
    }
    assert conn.dolly.stats()["totals"] == {
        "select": 3,
        "unknown": 0,
        "interventions": 0,
    }


def test_zero_weights_skip_decision_and_parameter_derivations(monkeypatch):
    conn = dogdb.wrap(_raw(), seed=42, faults={})

    def unexpected(*args, **kwargs):
        raise AssertionError("zero-weight fast path performed a derivation")

    monkeypatch.setattr(conn._decisions, "decide", unexpected)
    monkeypatch.setattr("dogdb.core.decision.parameter_fingerprint", unexpected)

    conn.execute("select id from t").fetchall()


def test_parameter_fingerprint_is_memoized_across_debug_phases(monkeypatch):
    calls = 0
    from dogdb.core import decision

    original = decision.parameter_fingerprint

    def counted(params, key):
        nonlocal calls
        calls += 1
        return original(params, key)

    monkeypatch.setattr(decision, "parameter_fingerprint", counted)
    conn = dogdb.wrap(_raw(), seed=42, faults={}, debug=True)

    conn.execute("select id from t").fetchall()

    assert calls == 1
