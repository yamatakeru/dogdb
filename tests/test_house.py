from __future__ import annotations

import sqlite3

import dogdb
from dogdb.core.house import rebuild_house


def _connection(rows: int = 5):
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(index,) for index in range(rows)])
    return dogdb.wrap(raw, seed=42, faults={"STASH": 1})


def test_stash_is_sticky_without_duplicate_treasures():
    conn = _connection()
    first = conn.execute("select id from t").fetchall()
    for _ in range(3):
        assert conn.execute("select id from t").fetchall() == first
    assert len(conn.dolly.house()) == 1


def test_return_all_restores_rows_and_logs_return():
    conn = _connection()
    assert len(conn.execute("select id from t").fetchall()) == 4
    conn.dolly.return_all()
    assert len(conn.execute("select id from t").fetchall()) == 5
    assert conn.dolly.log()[-1].event_type == "treasure_returned"


def test_house_exposes_value_and_identity_fields():
    conn = _connection()
    conn.execute("select id from t").fetchall()
    treasure = conn.dolly.house()[0]
    assert treasure.treasure_id
    assert treasure.template_fingerprint.startswith("sha256:")
    assert isinstance(treasure.row_index, int)
    assert treasure.row in [(index,) for index in range(5)]
    assert treasure.event_id


def test_log_projection_matches_house_after_partial_return():
    raw = sqlite3.connect(":memory:")
    raw.execute("create table a(id integer)")
    raw.execute("create table b(id integer)")
    raw.executemany("insert into a values (?)", [(1,), (2,)])
    raw.executemany("insert into b values (?)", [(3,), (4,)])
    conn = dogdb.wrap(raw, seed=7, faults={"STASH": 1})
    conn.execute("select id from a").fetchall()
    conn.execute("select id from b").fetchall()
    conn.dolly.return_treasure(conn.dolly.house()[0].treasure_id)

    projected = rebuild_house(conn.dolly.log())
    assert {item.treasure_id for item in projected} == {
        item.treasure_id for item in conn.dolly.house()
    }
