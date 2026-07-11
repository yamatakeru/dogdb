"""Deterministic MVP behavior demonstration used for task 6.3."""

from __future__ import annotations

import sqlite3

import dogdb
from dogdb import DollyIgnoredError, DollyStashedError


def database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(index,) for index in range(10)])
    return raw


def main() -> None:
    stash = dogdb.wrap(database(), seed=0, faults={"STASH": 1})
    print("STASH rows:", stash.execute("select id from t").fetchall())
    print("conn.dolly.house():", stash.dolly.house())

    stash_error = dogdb.wrap(
        database(), seed=0, faults={"STASH": 1}, stash_mode="error"
    )
    try:
        stash_error.execute("select id from t")
    except DollyStashedError as error:
        print(str(error))

    shuffle = dogdb.wrap(database(), seed=0, faults={"SHUFFLE": 1})
    print("SHUFFLE rows:", shuffle.execute("select id from t").fetchall())

    ignored_raw = database()
    ignored = dogdb.wrap(ignored_raw, seed=0, faults={"IGNORE": 1})
    try:
        ignored.execute("insert into t values (10)")
    except DollyIgnoredError as error:
        print("IGNORE:", error.outcome, "retryable=", error.retryable)
    print("IGNORE backend row count:", ignored_raw.execute("select count(*) from t").fetchone()[0])


if __name__ == "__main__":
    main()
