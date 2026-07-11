"""mood、自動返却、OLD_BONEを明示opt-inする例。"""

import sqlite3

import dogdb


def database(value: str = "最初のほね") -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    _ = raw.execute("create table treats(id integer, name text)")
    _ = raw.executemany(
        "insert into treats values (?, ?)",
        [(1, value), (2, "ボール"), (3, "ロープ")],
    )
    return raw


mood = dogdb.wrap(
    database(),
    seed=42,
    session_id="mood-example",
    mood={"epoch_length": 2},
)
for _ in range(8):
    _ = mood.execute("select id from treats order by id").fetchall()
print(
    "mood遷移:",
    [event.details for event in mood.dolly.log() if event.event_type == "mood_changed"],
)

returning = dogdb.wrap(
    database(),
    seed=42,
    faults={"STASH": 1.0},
    auto_return=(1, 1),
)
_ = returning.execute("select id, name from treats order by id").fetchall()
print(f"STASH直後のhouse件数: {len(returning.dolly.house())}")
_ = returning.execute("pragma user_version").fetchall()
print(f"1操作後に自動返却: {returning.dolly.house() == []}")

old_bone = dogdb.wrap(database(), seed=42, faults={"OLD_BONE": 1.0})
first = old_bone.execute("select name from treats where id = 1").fetchall()
_ = old_bone.execute("update treats set name = '新しいほね' where id = 1")
stale = old_bone.execute("select name from treats where id = 1").fetchall()
print(f"最初の配達結果: {first}")
print(f"OLD_BONEが返した過去結果: {stale}")
print(f"匿名stats: {old_bone.dolly.stats()}")
