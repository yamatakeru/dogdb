"""DogDB を pytest フィクスチャで使う最小例。"""

import sqlite3
from collections.abc import Iterator

import dogdb
import pytest
from dogdb.proxy import SQLiteProxy


@pytest.fixture
def conn() -> Iterator[SQLiteProxy]:
    raw = sqlite3.connect(":memory:")
    _ = raw.execute("create table treats(id integer, name text)")
    _ = raw.executemany(
        "insert into treats values (?, ?)",
        [(1, "ほね"), (2, "ボール"), (3, "ロープ")],
    )
    wrapped = dogdb.wrap(
        raw,
        seed=42,
        # テストでは必ず STASH し、耐障害処理を確実に通す。
        faults={"STASH": 1.0},
    )
    yield wrapped
    wrapped.close()


def load_all_treats(
    conn: SQLiteProxy, expected_count: int
) -> list[tuple[int, str]]:
    """欠落を検知したら隠された行を返し、同じ読取りを再試行する。"""
    sql = "select id, name from treats order by id"
    rows = conn.execute(sql).fetchall()
    if len(rows) != expected_count and conn.dolly.house():
        _ = conn.dolly.return_all()
        rows = conn.execute(sql).fetchall()
    return rows


def test_application_recovers_from_stash(conn: SQLiteProxy) -> None:
    rows = load_all_treats(conn, expected_count=3)

    assert rows == [(1, "ほね"), (2, "ボール"), (3, "ロープ")]
    events = conn.dolly.log()
    assert [event.event_type for event in events] == [
        "fault_injected",
        "treasure_returned",
    ]
    assert events[0].fault == "STASH"
    assert events[0].outcome == "rows_hidden"
    assert conn.dolly.house() == []
