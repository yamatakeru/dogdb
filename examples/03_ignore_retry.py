"""IGNORE を retryable 属性で判定して再試行する例。"""

import sqlite3
from typing import cast

import dogdb
from dogdb import DollyIgnoredError


raw = sqlite3.connect(":memory:")
_ = raw.execute("create table requests(id integer primary key, body text)")

first_attempt = dogdb.wrap(
    raw,
    seed=42,
    # 最初の試行は必ず IGNORE され、未実行であることを確実に示す。
    faults={"IGNORE": 1.0},
)
retry_attempt = dogdb.wrap(raw, seed=42)

sql = "insert into requests values (?, ?)"
params = (1, "おやつをください")

try:
    _ = first_attempt.execute(sql, params)
except DollyIgnoredError as error:
    print(
        "IGNORE を捕捉:",
        f"retryable={error.retryable}, outcome={error.outcome}",
    )
    count_after_ignore = cast(
        int,
        raw.execute("select count(*) from requests").fetchone()[0],
    )
    print(f"IGNORE 直後の行数（未実行）: {count_after_ignore}")
    if error.retryable:
        _ = retry_attempt.execute(sql, params)
        print("再試行: 成功")

rows = raw.execute("select id, body from requests order by id").fetchall()
print(f"最終行: {rows}")
print(f"二重実行なし: {len(rows) == 1}")
