"""SHUFFLE で暗黙の行順序に依存するバグを見つける例。"""

import sqlite3

import dogdb


def minimum_balance(rows: list[tuple[int]]) -> int:
    """取得順を時系列だと思い込んだ、バグのある集計コード。"""
    balance = 0
    lowest = 0
    for (change,) in rows:
        balance += change
        lowest = min(lowest, balance)
    return lowest


raw = sqlite3.connect(":memory:")
raw.execute("create table transactions(seq integer, change integer)")
raw.executemany(
    "insert into transactions values (?, ?)",
    [(1, 100), (2, -80), (3, -10)],
)

conn = dogdb.wrap(
    raw,
    seed=42,
    # ORDER BY のない SELECT では必ず SHUFFLE し、バグを確実に再現する。
    faults={"SHUFFLE": 1.0},
)

unordered = conn.execute("select change from transactions").fetchall()
print(f"ORDER BY なしの取得順: {unordered}")
print(f"バグのある最低残高: {minimum_balance(unordered)}")
print(f"注入された障害: {[event.fault for event in conn.dolly.log()]}")

ordered = conn.execute(
    "select change from transactions order by seq"
).fetchall()
print(f"ORDER BY ありの取得順: {ordered}")
print(f"正しい最低残高: {minimum_balance(ordered)}")
print(f"イベント数（ORDER BY では増えない）: {len(conn.dolly.log())}")
