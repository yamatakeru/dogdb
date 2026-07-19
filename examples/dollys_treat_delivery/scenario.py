"""Deterministic scenarios for Dolly's first delivery shift."""

from __future__ import annotations

import sqlite3
from typing import Any

import dogdb

ACTS = frozenset(("normal", "dolly", "fixed"))
ORDER_ID = "TREAT-042"
SEED = 42
SESSION_ID = "dolly-first-shift"
BUGGY_SQL = """\
select sequence, status
from order_events
where order_id = ?"""
FIXED_SQL = f"{BUGGY_SQL}\norder by sequence"

SOURCE_EVENTS = (
    (1, "ORDERED"),
    (2, "PACKED"),
    (3, "OUT_FOR_DELIVERY"),
    (4, "DELIVERED"),
)


def run_act(act: str) -> dict[str, Any]:
    """Run one tutorial act against a fresh database."""
    if act not in ACTS:
        raise ValueError(f"unknown tutorial act: {act}")

    raw = _database()
    faults = {"SHUFFLE": 1.0} if act != "normal" else {}
    sql = FIXED_SQL if act == "fixed" else BUGGY_SQL
    conn = dogdb.wrap(
        raw,
        seed=SEED,
        session_id=SESSION_ID,
        faults=faults,
    )
    try:
        rows = conn.execute(sql, (ORDER_ID,)).fetchall()
        events = [_event_payload(event) for event in conn.dolly.log()]
    finally:
        conn.close()

    delivered = [_row_payload(row) for row in rows]
    expected_status = SOURCE_EVENTS[-1][1]
    observed_status = delivered[-1]["status"]
    return {
        "act": act,
        "order_id": ORDER_ID,
        "product": "Bone Biscuit Refill",
        "sql": sql,
        "source_events": [_row_payload(row) for row in SOURCE_EVENTS],
        "delivered_events": delivered,
        "expected_status": expected_status,
        "observed_status": observed_status,
        "passed": observed_status == expected_status,
        "events": events,
        "seed": SEED,
        "session_id": SESSION_ID,
    }


def _database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute(
        """create table order_events(
            order_id text not null,
            sequence integer not null,
            status text not null
        )"""
    )
    raw.executemany(
        "insert into order_events values (?, ?, ?)",
        [(ORDER_ID, sequence, status) for sequence, status in SOURCE_EVENTS],
    )
    return raw


def _row_payload(row: tuple[int, str]) -> dict[str, int | str]:
    sequence, status = row
    return {"sequence": sequence, "status": status}


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "fault": event.fault,
        "phase": event.phase,
        "occurrence": event.occurrence,
        "outcome": event.outcome,
        "category": event.category,
        "severity": event.severity,
        "details": event.details,
    }
