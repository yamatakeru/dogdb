from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import dogdb


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "policy_v4_golden.json").read_text()
)


def _run(fault: str) -> dict[str, object]:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer)")
    raw.executemany("insert into t values (?)", [(0,), (1,), (2,), (3,), (4,)])
    conn = dogdb.wrap(
        raw,
        seed=42,
        session_id=f"fixture-{fault.lower()}",
        faults={fault: 1},
    )
    assert conn._mood is None
    error = None
    try:
        rows = conn.execute("select id from t").fetchall()
    except dogdb.DogDBError as caught:
        rows = None
        error = {
            "type": type(caught).__name__,
            "event_id": caught.event_id,
            "fault": caught.fault,
            "phase": caught.phase,
            "retryable": caught.retryable,
            "outcome": caught.outcome,
        }
    events = [asdict(event) for event in conn.dolly.log()]
    return json.loads(json.dumps({"rows": rows, "error": error, "events": events}))


def test_policy_fault_outputs_remain_bit_for_bit_stable():
    assert {fault: _run(fault) for fault in ("STASH", "SHUFFLE", "IGNORE")} == FIXTURE
