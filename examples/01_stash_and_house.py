"""STASH で隠れた行を house から返す例。"""

import sqlite3

import dogdb


raw = sqlite3.connect(":memory:")
raw.execute("create table treasures(id integer, name text)")
raw.executemany(
    "insert into treasures values (?, ?)",
    [(1, "ほね"), (2, "ボール"), (3, "ロープ")],
)

conn = dogdb.wrap(
    raw,
    seed=42,
    # 実行のたびに必ず STASH を発火させ、例を決定的にする。
    faults={"STASH": 1.0},
)
sql = "select id, name from treasures"

first = conn.execute(sql).fetchall()
hidden = conn.dolly.house()[0].row
print(f"1回目（1行欠落）: {first}")
print(f"ドリーの house: {[item.row for item in conn.dolly.house()]}")

second = conn.execute(sql).fetchall()
print(f"2回目（同じ行が隠れ続ける）: {second}")
print(f"粘着性を確認: {hidden not in first and hidden not in second}")

conn.dolly.return_all()
restored = conn.execute(sql).fetchall()
print(f"return_all() 後: {restored}")
print(f"house は空: {conn.dolly.house() == []}")
