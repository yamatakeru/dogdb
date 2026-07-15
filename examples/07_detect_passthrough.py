"""on_passthrough で「注入したつもり」の素通しを検出する例。"""

import sqlite3
import warnings
from typing import cast

import dogdb


def database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    _ = raw.execute("create table treats(id integer, name text)")
    _ = raw.executemany(
        "insert into treats values (?, ?)",
        [(1, "ほね"), (2, "ボール"), (3, "ロープ")],
    )
    return raw


print("1. 罠の再現（既定 allow）")
allowed = dogdb.wrap(
    database(),
    seed=42,
    # 名前付きパラメータは障害注入の対象外なので、STASHは発火しない。
    faults={"STASH": 1.0},
)
sql = "select id, name from treats where id >= :min_id"
allowed_rows = allowed.execute(sql, {"min_id": 1}).fetchall()
print(f"STASH 1.0でも全行返る: {allowed_rows}")
print(f"障害イベントなし: {allowed.dolly.log() == []}")
print(f"素通しstats: {allowed.dolly.stats()['passthrough']}")
allowed.close()

print("\n2. warnで通知")
warned = dogdb.wrap(
    database(),
    seed=42,
    faults={"STASH": 1.0},
    on_passthrough="warn",
)
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    warned_rows = warned.execute(sql, {"min_id": 1}).fetchall()
warning = caught[0].message
print(f"捕捉した警告: {type(warning).__name__}: {warning}")
print(f"警告後も全行返る: {warned_rows}")
warned.close()

print("\n3. errorで遮断")
raw = sqlite3.connect(":memory:")
_ = raw.execute("create table treats(id integer, name text)")
blocked = dogdb.wrap(raw, seed=42, on_passthrough="error")
try:
    _ = blocked.execute(
        "insert into treats values (:id, :name)",
        {"id": 1, "name": "ほね"},
    )
except dogdb.DollyPassthroughError as error:
    print(f"捕捉した例外: {type(error).__name__}: {error}")
    print(f"再試行不可: retryable={error.retryable}")
else:
    raise AssertionError("DollyPassthroughErrorが送出されませんでした")
row_count = cast(
    int,
    raw.execute("select count(*) from treats").fetchone()[0],
)
print(f"バックエンド実行前に遮断（行数）: {row_count}")
print(f"遮断済みでもstatsへ記録: {blocked.dolly.stats()['passthrough']}")
blocked.close()

print("\n4. 対象外の理由キー")
transactions = dogdb.wrap(
    sqlite3.connect(":memory:"),
    seed=42,
    on_passthrough="error",
)
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    _ = transactions.execute("begin")
    transactions.rollback()
print(f"errorモードでもBEGIN／ROLLBACK成功、警告なし: {caught == []}")
print(f"transaction_statement stats: {transactions.dolly.stats()['passthrough']}")
transactions.close()
