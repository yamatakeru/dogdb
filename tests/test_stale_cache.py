from __future__ import annotations

import sqlite3

import dogdb

from dogdb.core.fingerprints import template_fingerprint
from dogdb.core.models import Decision, LogicalResult
from dogdb.core.stale_cache import StaleReadCache


def _raw(secret: str = "first-secret") -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, secret text)")
    raw.execute("insert into t values (1, ?)", (secret,))
    return raw


def test_old_bone_returns_a_previous_delivered_result():
    conn = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
    first = conn.execute("select secret from t where id = 1").fetchall()
    conn.execute("update t set secret = 'second-secret' where id = 1")
    stale = conn.execute("select secret from t where id = 1").fetchall()
    event = conn.dolly.log()[0]

    assert first == [("first-secret",)]
    assert stale == first
    assert event.fault == "OLD_BONE"
    assert event.outcome == "stale_read"
    assert event.details == {"stale_occurrence": 1}


def test_initial_select_has_no_old_bone_candidate():
    conn = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
    assert conn.execute("select secret from t").fetchall() == [("first-secret",)]
    assert conn.dolly.log() == []
    assert len(conn._stale_cache.entries()) == 1


def test_cache_stores_the_client_delivered_stash_result():
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,), (4,), (5,)])
    conn = dogdb.wrap(raw, seed=42, faults={"STASH": 1, "OLD_BONE": 1})
    delivered = conn.execute("select id from t order by id").fetchall()
    cached = conn._stale_cache.entries()[0]

    assert len(delivered) == 4
    assert cached.occurrence == 1
    assert cached.result.rows == delivered


def test_parameter_fingerprint_partitions_cache_only_when_enabled():
    faithful = dogdb.wrap(
        _raw(), seed=42, include_params=True, faults={"OLD_BONE": 1}
    )
    faithful.execute("select secret from t where ? is not null", ("a",)).fetchall()
    faithful.execute("select secret from t where ? is not null", ("b",)).fetchall()
    assert faithful.dolly.log() == []
    faithful.execute("select secret from t where ? is not null", ("a",)).fetchall()
    assert faithful.dolly.log()[0].fault == "OLD_BONE"

    default = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
    default.execute("select secret from t where ? is not null", ("a",)).fetchall()
    default.execute("select secret from t where ? is not null", ("b",)).fetchall()
    assert default.dolly.log()[0].fault == "OLD_BONE"


def test_per_fingerprint_ring_evicts_oldest_occurrence():
    conn = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
    for _ in range(5):
        conn.execute("select secret from t").fetchall()

    assert [entry.occurrence for entry in conn._stale_cache.entries()] == [2, 3, 4, 5]


def test_total_cache_eviction_is_deterministic():
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(_raw(), seed=42, faults={"OLD_BONE": 1})
        for index in range(65):
            conn.execute(f"select secret from t where id >= {index}").fetchall()
        entries = conn._stale_cache.entries()
        runs.append([(entry.key, entry.occurrence) for entry in entries])
    assert runs[0] == runs[1]
    assert len(runs[0]) == 64
    first_key = (template_fingerprint("select secret from t where id >= 0"), None)
    assert all(key != first_key for key, _ in runs[0])


def test_oversized_result_is_not_cached():
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    conn = dogdb.wrap(raw, seed=42, faults={"OLD_BONE": 1}, max_rows=2)
    conn.execute("select id from t").fetchall()
    assert conn._stale_cache.entries() == []


def test_oversized_missing_keys_do_not_accumulate_empty_history_entries():
    cache = StaleReadCache(include_params=False, max_rows=1)
    oversized = LogicalResult(["id"], [(1,), (2,)], 2)

    for occurrence in range(100):
        decision = Decision(
            template_fingerprint=f"sha256:missing-{occurrence}",
            parameter_fingerprint="hmac-sha256:ignored",
            occurrence=occurrence,
            phase="on_result",
            decision_key=f"sha256:decision-{occurrence}",
        )
        assert cache.history(decision) == []
        assert cache.add(decision, oversized) is False

    assert cache.entries() == []
    assert len(cache._by_key) == 0


def test_cached_and_corrupted_values_never_appear_in_log(tmp_path):
    path = tmp_path / "events.jsonl"
    conn = dogdb.wrap(
        _raw("cache-secret-value"),
        seed=42,
        faults={"OLD_BONE": 1},
        log_path=path,
    )
    conn.execute("select secret from t").fetchall()
    conn.execute("update t set secret = 'new-secret-value'")
    conn.execute("select secret from t").fetchall()

    contents = path.read_text()
    assert "cache-secret-value" not in contents
    assert "new-secret-value" not in contents
    assert conn.dolly.log()[-1].details == {"stale_occurrence": 1}


def test_old_bone_runs_are_deterministic():
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            _raw(), seed=42, session_id="old-bone-replay", faults={"OLD_BONE": 1}
        )
        rows = [conn.execute("select secret from t").fetchall() for _ in range(6)]
        runs.append((rows, conn.dolly.log(), conn._stale_cache.entries()))
    assert runs[0] == runs[1]


def test_old_bone_disabled_does_not_allocate_cache():
    conn = dogdb.wrap(_raw(), seed=42)
    assert conn._stale_cache is None
