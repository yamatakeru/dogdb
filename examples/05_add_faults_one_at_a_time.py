"""新しい障害を別セッションで1個ずつ試す例。"""

import sqlite3

import dogdb


def database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    _ = raw.execute("create table treats(id integer, name text)")
    _ = raw.executemany(
        "insert into treats values (?, ?)",
        [(1, "ほね"), (2, "ボール"), (3, "ロープ")],
    )
    return raw


echo = dogdb.wrap(database(), seed=42, faults={"ECHO": 1.0})
echo_rows = echo.execute("select id, name from treats order by id").fetchall()
print(f"ECHOだけを有効化: {echo_rows}")
print(f"イベント: {[(event.fault, event.outcome) for event in echo.dolly.log()]}")

sleeps: list[float] = []
sloth = dogdb.wrap(
    database(),
    seed=42,
    faults={"SLOTH": 1.0},
    # time.sleepと同じ秒単位引数を受け取り、実際には待たない。
    clock=sleeps.append,
)
sloth_rows = sloth.execute("select id, name from treats order by id").fetchall()
print(f"SLOTHだけを有効化（待ち時間なし）: {sloth_rows}")
sloth_details = sloth.dolly.log()[0].details
assert sloth_details is not None
print(f"論理遅延: {sloth_details['delay_ms']}ms")
print(f"clockへ渡された秒数: {sleeps}")
