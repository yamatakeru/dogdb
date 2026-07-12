from __future__ import annotations

import sqlite3
import statistics
import time
from collections.abc import Callable

import dogdb


SELECTS = 2_000
WARMUPS = 3
REPETITIONS = 7
SQL = "select value from items order by id"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("create table items(id integer primary key, value text)")
    connection.executemany(
        "insert into items values (?, ?)",
        [(index, f"value-{index}") for index in range(32)],
    )
    return connection


def _run(execute: Callable[..., object]) -> None:
    for _ in range(SELECTS):
        cursor = execute(SQL)
        cursor.fetchall()  # type: ignore[attr-defined]


def _measure(execute: Callable[..., object]) -> list[float]:
    for _ in range(WARMUPS):
        _run(execute)
    samples = []
    for _ in range(REPETITIONS):
        started = time.perf_counter()
        _run(execute)
        samples.append(time.perf_counter() - started)
    return samples


def main() -> None:
    bare = _connection()
    wrapped = dogdb.wrap(_connection(), seed=42, faults={})

    bare_median = statistics.median(_measure(bare.execute))
    wrapped_median = statistics.median(_measure(wrapped.execute))
    ratio = wrapped_median / bare_median

    print(f"bare median: {bare_median * 1_000:.3f} ms")
    print(f"wrapped median: {wrapped_median * 1_000:.3f} ms")
    print(f"wrapped/bare ratio: {ratio:.3f}x")


if __name__ == "__main__":
    main()
