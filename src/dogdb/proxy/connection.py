"""DB-API connection proxy and public constructors."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dogdb.adapters.duckdb import DuckDBAdapter
from dogdb.adapters.sqlite import SQLiteAdapter
from dogdb.core.decision import DecisionEngine
from dogdb.core.event_log import Event, EventLog
from dogdb.core.faults import FaultEngine, FaultPolicy
from dogdb.core.house import HouseLedger, Treasure
from dogdb.core.models import LogicalResult
from dogdb.core.sql import SQLKind, classify_sql


class DollyNamespace:
    def __init__(self, proxy: DBAPIProxy) -> None:
        self._proxy = proxy

    def house(self) -> list[Treasure]:
        return self._proxy._house.values()

    def log(self) -> list[Event]:
        return self._proxy._events.events()

    def return_treasure(self, treasure_id: str) -> Treasure | None:
        treasure = self._proxy._house.return_treasure(treasure_id)
        if treasure is not None:
            self._log_return(treasure)
        return treasure

    def return_all(self) -> list[Treasure]:
        returned = self._proxy._house.return_all()
        for treasure in returned:
            self._log_return(treasure)
        return returned

    def _log_return(self, treasure: Treasure) -> None:
        seq = len(self._proxy._events.events()) + 1
        event_id = self._proxy._decisions.deterministic_id(
            treasure.decision_key, f"event:{seq}:RETURN"
        )
        self._proxy._events.append(
            event_id=event_id,
            event_type="treasure_returned",
            fault="STASH",
            phase="manual_return",
            template_fingerprint=treasure.template_fingerprint,
            parameter_fingerprint=treasure.parameter_fingerprint,
            occurrence=treasure.occurrence,
            decision_key=treasure.decision_key,
            outcome="treasure_returned",
            details={"treasure_id": treasure.treasure_id},
        )


class DBAPIProxy:
    def __init__(
        self,
        connection: Any,
        adapter: DuckDBAdapter | SQLiteAdapter,
        *,
        seed: object,
        session_id: str,
        include_params: bool,
        policy: FaultPolicy,
        log_path: str | Path | None,
        max_rows: int,
        house_limit: int,
    ) -> None:
        self._connection = connection
        self._adapter = adapter
        self._decisions = DecisionEngine(
            seed=seed, session_id=session_id, include_params=include_params
        )
        self._events = EventLog(session_id, log_path)
        self._house = HouseLedger(house_limit)
        self._faults = FaultEngine(
            self._decisions, self._events, self._house, policy, max_rows
        )
        self._result = LogicalResult([], [], -1)
        self._offset = 0
        self.dolly = DollyNamespace(self)

    def execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> DBAPIProxy:
        classification = classify_sql(sql)
        if (
            isinstance(params, Mapping)
            or classification.kind is SQLKind.UNKNOWN
            or classification.is_transaction
        ):
            self._result = self._adapter.execute(sql, params)  # type: ignore[arg-type]
            self._offset = 0
            return self

        template, parameter, occurrence = self._decisions.begin(sql, params)
        before = self._decisions.decide(
            template=template,
            parameter=parameter,
            occurrence=occurrence,
            phase="before_execute",
        )
        self._faults.before_execute(before)
        result = self._adapter.execute(sql, params)
        on_result = self._decisions.decide(
            template=template,
            parameter=parameter,
            occurrence=occurrence,
            phase="on_result",
        )
        self._result = self._faults.on_result(on_result, classification, result)
        self._offset = 0
        return self

    def executemany(self, sql: str, params: Sequence[Sequence[Any]]) -> DBAPIProxy:
        cursor = self._connection.executemany(sql, params)
        self._result = LogicalResult([], [], getattr(cursor, "rowcount", -1))
        self._offset = 0
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self._result.rows[self._offset :]
        self._offset = len(self._result.rows)
        return list(rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._offset >= len(self._result.rows):
            return None
        row = self._result.rows[self._offset]
        self._offset += 1
        return row

    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]:
        amount = 1 if size is None else size
        rows = self._result.rows[self._offset : self._offset + amount]
        self._offset += len(rows)
        return list(rows)

    @property
    def description(self) -> tuple[tuple[str, None, None, None, None, None, None], ...] | None:
        if not self._result.columns:
            return None
        return tuple((name, None, None, None, None, None, None) for name in self._result.columns)

    @property
    def rowcount(self) -> int:
        return self._result.rowcount

    @property
    def in_transaction(self) -> bool:
        return self._adapter.in_transaction

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._adapter.close()

    def __enter__(self) -> DBAPIProxy:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _adapter_for(connection: Any) -> DuckDBAdapter | SQLiteAdapter:
    module = type(connection).__module__
    if module.startswith("sqlite3"):
        return SQLiteAdapter(connection)
    if "duckdb" in module or "duckdb" in type(connection).__name__.lower():
        return DuckDBAdapter(connection)
    raise TypeError(f"unsupported connection type: {type(connection)!r}")


def wrap(
    connection: Any,
    *,
    seed: object,
    session_id: str | None = None,
    include_params: bool = False,
    fault_probabilities: Mapping[str, float] | None = None,
    faults: Mapping[str, float] | None = None,
    stash_mode: str = "missing",
    log_path: str | Path | None = None,
    event_log: str | Path | None = None,
    max_rows: int = 10_000,
    house_limit: int = 1_000,
) -> DBAPIProxy:
    probabilities = {"STASH": 0.0, "SHUFFLE": 0.0, "IGNORE": 0.0}
    supplied = fault_probabilities if fault_probabilities is not None else faults
    if supplied:
        probabilities.update({str(key).upper(): value for key, value in supplied.items()})
    unknown = set(probabilities) - {"STASH", "SHUFFLE", "IGNORE"}
    if unknown:
        raise ValueError(f"unknown faults: {', '.join(sorted(unknown))}")
    if session_id is None:
        digest = hashlib.sha256(f"dogdb-session\0{seed}".encode()).hexdigest()[:24]
        session_id = f"session-{digest}"
    return DBAPIProxy(
        connection,
        _adapter_for(connection),
        seed=seed,
        session_id=session_id,
        include_params=include_params,
        policy=FaultPolicy(
            stash=probabilities["STASH"],
            shuffle=probabilities["SHUFFLE"],
            ignore=probabilities["IGNORE"],
            stash_mode=stash_mode,
        ),
        log_path=log_path if log_path is not None else event_log,
        max_rows=max_rows,
        house_limit=house_limit,
    )


def connect(
    path: str = ":memory:",
    *,
    backend: str = "duckdb",
    seed: object,
    **options: Any,
) -> DBAPIProxy:
    if backend == "sqlite":
        import sqlite3

        connection = sqlite3.connect(path)
    elif backend == "duckdb":
        import duckdb

        connection = duckdb.connect(path)
    else:
        raise ValueError("backend must be 'duckdb' or 'sqlite'")
    return wrap(connection, seed=seed, **options)
