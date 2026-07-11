from __future__ import annotations

import json
import sqlite3

import dogdb

from dogdb.core.fingerprints import template_fingerprint


def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    return raw


def test_stats_report_anonymous_classification_and_interventions():
    conn = dogdb.wrap(_raw(), seed=42, faults={"ECHO": 1})
    select_sql = "select id from t order by id"
    unknown_sql = "with values_cte as (select 1) select * from values_cte"
    conn.execute(select_sql).fetchall()
    conn.execute(unknown_sql).fetchall()

    stats = conn.dolly.stats()
    select_key = template_fingerprint(select_sql)
    unknown_key = template_fingerprint(unknown_sql)

    assert stats["fingerprints"][select_key] == {
        "select": 1,
        "unknown": 0,
        "interventions": 1,
    }
    assert stats["fingerprints"][unknown_key] == {
        "select": 0,
        "unknown": 1,
        "interventions": 0,
    }
    assert stats["totals"] == {"select": 1, "unknown": 1, "interventions": 1}


def test_stats_count_sticky_stash_as_intervention_each_time():
    conn = dogdb.wrap(_raw(), seed=42, faults={"STASH": 1})
    sql = "select id from t order by id"
    for _ in range(4):
        conn.execute(sql).fetchall()

    assert conn.dolly.stats()["fingerprints"][template_fingerprint(sql)] == {
        "select": 4,
        "unknown": 0,
        "interventions": 4,
    }


def test_return_events_do_not_increment_query_interventions():
    conn = dogdb.wrap(
        _raw(), seed=42, faults={"STASH": 1}, auto_return=(1, 1)
    )
    sql = "select id from t order by id"
    conn.execute(sql).fetchall()
    conn.execute("pragma user_version").fetchall()

    assert conn.dolly.stats()["fingerprints"][template_fingerprint(sql)][
        "interventions"
    ] == 1


def test_stats_contain_no_raw_sql_or_parameters():
    conn = dogdb.wrap(_raw(), seed=42, faults={"ECHO": 1})
    sql = "select id from t where ? = 'raw-sql-secret'"
    parameter = "raw-parameter-secret"
    conn.execute(sql, (parameter,)).fetchall()

    payload = json.dumps(conn.dolly.stats(), sort_keys=True)
    assert "raw-sql-secret" not in payload
    assert "raw-parameter-secret" not in payload
    assert "select id" not in payload.lower()


def test_stats_snapshot_is_detached_from_internal_state():
    conn = dogdb.wrap(_raw(), seed=42)
    conn.execute("select id from t").fetchall()
    snapshot = conn.dolly.stats()
    snapshot["totals"]["select"] = 999
    assert conn.dolly.stats()["totals"]["select"] == 1
