"""DB-API connection proxy and public constructors."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from dogdb.adapters.base import Adapter
from dogdb.adapters.duckdb import DuckDBAdapter
from dogdb.adapters.sqlite import SQLiteAdapter
from dogdb.core.auto_return import AutoReturnScheduler, parse_auto_return_config
from dogdb.core.decision import DecisionEngine
from dogdb.core.event_log import Event, EventLog
from dogdb.core.faults import KNOWN_FAULTS, FaultEngine, FaultPolicy
from dogdb.core.house import HouseLedger, Treasure
from dogdb.core.fingerprints import (
    params_in_fingerprint_domain,
    template_fingerprint,
)
from dogdb.core.models import LogicalResult
from dogdb.core.mood import MoodEngine, parse_mood_config
from dogdb.core.sql import SQLKind, classify_sql
from dogdb.core.stale_cache import StaleReadCache
from dogdb.core.stats import StatsTracker


class DollyNamespace:
    def __init__(self, engine: _InterventionEngine) -> None:
        self._engine = engine

    def house(self) -> list[Treasure]:
        return self._engine._house.values()

    def log(self) -> list[Event]:
        return self._engine._events.events()

    def stats(self) -> dict[str, object]:
        return self._engine._stats.snapshot()

    def return_treasure(self, treasure_id: str) -> Treasure | None:
        if self._engine._auto_return is not None:
            self._engine._auto_return.cancel(treasure_id)
        treasure = self._engine._house.return_treasure(treasure_id)
        if treasure is not None:
            self._log_return(treasure)
        return treasure

    def return_all(self) -> list[Treasure]:
        returned = self._engine._house.return_all()
        for treasure in returned:
            if self._engine._auto_return is not None:
                self._engine._auto_return.cancel(treasure.treasure_id)
            self._log_return(treasure)
        return returned

    def _log_return(self, treasure: Treasure, *, phase: str = "manual_return") -> None:
        seq = self._engine._events.next_seq()
        tag = f"event:{seq}:RETURN"
        event_id = self._engine._decisions.deterministic_id(treasure.decision_key, tag)
        self._engine._events.append(
            event_id=event_id,
            event_type="treasure_returned",
            fault="STASH",
            phase=phase,
            template_fingerprint=treasure.template_fingerprint,
            parameter_fingerprint=treasure.parameter_fingerprint,
            occurrence=treasure.occurrence,
            decision_key=treasure.decision_key,
            outcome="treasure_returned",
            details={"treasure_id": treasure.treasure_id},
        )


class _InterventionEngine:
    def __init__(
        self,
        connection: Any,
        adapter: Adapter,
        *,
        seed: object,
        session_id: str,
        include_params: bool,
        policy: FaultPolicy,
        log_path: str | Path | None,
        max_intervention_rows: int,
        house_limit: int,
        only_tables: frozenset[str] | None,
        exclude_tables: frozenset[str] | None,
        debug: bool,
        clock: Callable[[float], None],
        mood: MoodEngine | None,
        auto_return: AutoReturnScheduler | None,
        stale_cache: StaleReadCache | None,
        stats: StatsTracker,
    ) -> None:
        self._connection = connection
        self._adapter = adapter
        self._decisions = DecisionEngine(
            seed=seed, session_id=session_id, include_params=include_params
        )
        self._events = EventLog(session_id, log_path)
        self._house = HouseLedger(house_limit)
        self._faults = FaultEngine(
            self._decisions,
            self._events,
            self._house,
            policy,
            max_intervention_rows,
            debug,
            clock,
            mood,
            auto_return,
            stale_cache,
            stats.record_intervention,
        )
        self._mood = mood
        self._auto_return = auto_return
        self._stale_cache = stale_cache
        self._stats = stats
        self._logical_tick = 0 if mood is not None or auto_return is not None else None
        self._only_tables = only_tables
        self._exclude_tables = exclude_tables
        self.dolly = DollyNamespace(self)

    def execute(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> LogicalResult:
        self._begin_operation()
        classification = classify_sql(sql)
        fingerprint = template_fingerprint(sql)
        self._stats.record_classification(fingerprint, classification.kind)
        is_mapping = isinstance(params, Mapping)
        unsupported_params = not is_mapping and not params_in_fingerprint_domain(params)
        if unsupported_params:
            self._stats.record_passthrough("unsupported_parameter_type")
        if (
            is_mapping
            or classification.kind is SQLKind.UNKNOWN
            or classification.is_transaction
            or unsupported_params
        ):
            return self._adapter.execute(sql, params)  # type: ignore[arg-type]

        template, parameter, occurrence = self._decisions.begin(sql, params)
        before = self._decisions.decide(
            template=template,
            parameter=parameter,
            occurrence=occurrence,
            phase="before_execute",
        )
        scoped = self._scope_applies(classification.tables)
        before_consumed = self._faults.before_execute(before) if scoped else False
        result = self._adapter.execute(sql, params)
        on_result = self._decisions.decide(
            template=template,
            parameter=parameter,
            occurrence=occurrence,
            phase="on_result",
        )
        logical_result = (
            self._faults.on_result(on_result, classification, result)
            if scoped and not before_consumed
            else result
        )
        if (
            self._stale_cache is not None
            and scoped
            and classification.kind is SQLKind.SELECT
        ):
            self._stale_cache.add(on_result, logical_result)
        return logical_result

    def _begin_operation(self) -> None:
        if self._logical_tick is None:
            return
        self._logical_tick += 1
        if self._auto_return is not None:
            for treasure_id in self._auto_return.advance(self._logical_tick):
                treasure = self._house.return_treasure(treasure_id)
                if treasure is not None:
                    self.dolly._log_return(treasure, phase="auto_return")
        if self._mood is None:
            return
        transition = self._mood.advance()
        assert self._mood.tick == self._logical_tick
        if transition is None:
            return
        seq = self._events.next_seq()
        self._events.append(
            event_id=self._decisions.deterministic_id(
                transition.derivation_key, f"event:{seq}:MOOD"
            ),
            event_type="mood_changed",
            details={
                "from": transition.previous,
                "to": transition.current,
                "tick": transition.tick,
            },
        )

    def _scope_applies(self, tables: frozenset[str] | None) -> bool:
        if self._only_tables is not None:
            return tables is not None and bool(tables & self._only_tables)
        if self._exclude_tables is not None:
            return tables is None or not bool(tables & self._exclude_tables)
        return True

    def executemany(self, sql: str, params: Sequence[Sequence[Any]]) -> LogicalResult:
        self._begin_operation()
        cursor = self._connection.executemany(sql, params)
        return LogicalResult([], [], getattr(cursor, "rowcount", -1))


class _EngineBackedSurface:
    """Private intervention-engine plumbing shared by public surfaces."""

    def __init__(
        self,
        connection: Any,
        adapter: Adapter,
        *,
        allow_native_passthrough: bool,
        **engine_options: Any,
    ) -> None:
        self._engine = _InterventionEngine(connection, adapter, **engine_options)
        self._connection = connection
        self._allow_native_passthrough = allow_native_passthrough
        self.dolly = self._engine.dolly

    @property
    def _adapter(self) -> Adapter:
        return self._engine._adapter

    @_adapter.setter
    def _adapter(self, adapter: Adapter) -> None:
        self._engine._adapter = adapter

    @property
    def _decisions(self) -> DecisionEngine:
        return self._engine._decisions

    @property
    def _events(self) -> EventLog:
        return self._engine._events

    @property
    def _faults(self) -> FaultEngine:
        return self._engine._faults

    @property
    def _mood(self) -> MoodEngine | None:
        return self._engine._mood

    @property
    def _auto_return(self) -> AutoReturnScheduler | None:
        return self._engine._auto_return

    @property
    def _stale_cache(self) -> StaleReadCache | None:
        return self._engine._stale_cache

    @property
    def _stats(self) -> StatsTracker:
        return self._engine._stats

    @property
    def _logical_tick(self) -> int | None:
        return self._engine._logical_tick

    def _native_passthrough_or_guidance(self, name: str) -> tuple[bool, Any]:
        if self._allow_native_passthrough:
            native_attr = getattr(self._connection, name)
            if not callable(native_attr):
                return True, native_attr
            bucket = name if name in self._adapter.sql_capable_attrs else "other"

            def call_native(*args: Any, **kwargs: Any) -> Any:
                self._stats.record_escape_hatch(bucket)
                return native_attr(*args, **kwargs)

            return True, call_native
        if name in self._adapter.sql_capable_attrs:
            raise AttributeError(
                f"DogDB cannot inject faults through native connection attribute {name!r}. "
                "Use execute() or pass allow_native_passthrough=True to wrap()."
            )
        return False, None


class DuckDBProxy(_EngineBackedSurface):
    """DuckDB-faithful connection surface backed by the intervention engine."""

    def __init__(
        self,
        connection: Any,
        adapter: Adapter,
        *,
        allow_native_passthrough: bool,
        **engine_options: Any,
    ) -> None:
        super().__init__(
            connection,
            adapter,
            allow_native_passthrough=allow_native_passthrough,
            **engine_options,
        )
        self._result = LogicalResult([], [], -1)
        self._offset = 0

    def execute(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> DuckDBProxy:
        self._result = self._engine.execute(sql, params)
        self._offset = 0
        return self

    def executemany(self, sql: str, params: Sequence[Sequence[Any]]) -> DuckDBProxy:
        self._result = self._engine.executemany(sql, params)
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

    def __enter__(self) -> DuckDBProxy:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        handled, value = self._native_passthrough_or_guidance(name)
        if handled:
            return value
        raise AttributeError(
            f"DuckDBProxy has no supported attribute {name!r}. Supported public API: "
            "execute(), executemany(), fetchall(), fetchone(), fetchmany(), description, "
            "rowcount, in_transaction, commit(), rollback(), close(), dolly, and context "
            "management. Pass allow_native_passthrough=True to wrap() for intentional "
            "native access."
        )


_ROWCOUNT_VISIBLE_FAULTS = frozenset(
    {"FALSE_EMPTY", "TAIL_CHASE", "ECHO", "PAGE_HOLE", "WRONG_COUNT"}
)


class CursorProxy:
    """SQLite-faithful cursor surface with an intervention-backed result slot."""

    def __init__(self, engine: _InterventionEngine) -> None:
        self._engine = engine
        self._result = LogicalResult([], [], -1)
        self._offset = 0
        self._reported_rowcount = -1

    def execute(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> CursorProxy:
        event_count = len(self._engine._events.events())
        self._result = self._engine.execute(sql, params)
        self._offset = 0
        new_events = self._engine._events.events()[event_count:]
        # Native sqlite3 reports -1 for SELECT rowcount regardless of fetch
        # state; only faults whose declared symptom involves the result count
        # surface through rowcount. This fault set is provisional until the
        # fault-taxonomy change closes the vocabulary.
        count_intervened = any(
            event.event_type == "fault_injected"
            and event.fault in _ROWCOUNT_VISIBLE_FAULTS
            for event in new_events
        )
        self._reported_rowcount = (
            self._result.rowcount
            if count_intervened or not self._result.columns
            else -1
        )
        return self

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> CursorProxy:
        self._result = self._engine.executemany(sql, params)
        self._offset = 0
        self._reported_rowcount = self._result.rowcount
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

    def __iter__(self) -> CursorProxy:
        return self

    def __next__(self) -> tuple[Any, ...]:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    @property
    def description(
        self,
    ) -> tuple[tuple[str, None, None, None, None, None, None], ...] | None:
        if not self._result.columns:
            return None
        return tuple(
            (name, None, None, None, None, None, None)
            for name in self._result.columns
        )

    @property
    def rowcount(self) -> int:
        return self._reported_rowcount


class SQLiteProxy(_EngineBackedSurface):
    """SQLite-faithful connection surface backed by the intervention engine."""

    def __init__(
        self,
        connection: Any,
        adapter: Adapter,
        *,
        allow_native_passthrough: bool,
        **engine_options: Any,
    ) -> None:
        super().__init__(
            connection,
            adapter,
            allow_native_passthrough=allow_native_passthrough,
            **engine_options,
        )

    def execute(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> CursorProxy:
        return self.cursor().execute(sql, params)

    def executemany(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> CursorProxy:
        return self.cursor().executemany(sql, params)

    def cursor(self) -> CursorProxy:
        return CursorProxy(self._engine)

    @property
    def in_transaction(self) -> bool:
        return self._adapter.in_transaction

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._adapter.close()

    def __enter__(self) -> SQLiteProxy:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                # Native sqlite3 (3.12+) rolls back when the implicit commit
                # fails, then propagates the commit error (measured on 3.13).
                self.rollback()
                raise
        else:
            self.rollback()

    def __getattr__(self, name: str) -> Any:
        if name in {"fetchall", "fetchone", "fetchmany", "description", "rowcount"}:
            raise AttributeError(
                f"SQLiteProxy has no connection-level {name!r}; SQLite results belong "
                "to cursors. Use conn.execute(sql).fetchall() or cursor().execute(sql)."
            )
        handled, value = self._native_passthrough_or_guidance(name)
        if handled:
            return value
        raise AttributeError(
            f"SQLiteProxy has no supported attribute {name!r}. Supported public API: "
            "execute(), executemany(), cursor(), in_transaction, commit(), rollback(), "
            "close(), dolly, and context management. Pass allow_native_passthrough=True "
            "to wrap() for intentional native access."
        )


def _adapter_for(connection: Any) -> Adapter:
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
    allow_native_passthrough: bool = False,
    fault_probabilities: Mapping[str, float] | None = None,
    faults: Mapping[str, float] | None = None,
    stash_mode: str = "missing",
    tail_chase_mode: str = "silent",
    chew_profiles: Sequence[str] = (
        "utf8_truncate",
        "precision_loss",
        "nullify",
    ),
    wrong_count_max_delta: int = 1,
    sloth_max_delay_ms: int = 1_000,
    clock: Callable[[float], None] = time.sleep,
    mood: bool | Mapping[str, Any] | None = False,
    auto_return: bool | Mapping[str, Any] | Sequence[int] | None = False,
    log_path: str | Path | None = None,
    max_intervention_rows: int = 10_000,
    on_max_rows: str = "skip",
    house_limit: int = 1_000,
    only_tables: Sequence[str] | None = None,
    exclude_tables: Sequence[str] | None = None,
    debug: bool = False,
) -> DuckDBProxy | SQLiteProxy:
    if only_tables is not None and exclude_tables is not None:
        raise ValueError("only_tables and exclude_tables are mutually exclusive")
    if not callable(clock):
        raise ValueError("clock must be callable")
    probabilities: dict[str, float] = {}
    supplied = fault_probabilities if fault_probabilities is not None else faults
    if supplied:
        probabilities.update({str(key).upper(): value for key, value in supplied.items()})
    unknown = set(probabilities) - KNOWN_FAULTS
    if unknown:
        raise ValueError(f"unknown faults: {', '.join(sorted(unknown))}")
    if session_id is None:
        digest = hashlib.sha256(f"dogdb-session\0{seed}".encode()).hexdigest()[:24]
        session_id = f"session-{digest}"
    mood_config = parse_mood_config(mood)
    mood_engine = (
        MoodEngine(seed=seed, session_id=session_id, config=mood_config)
        if mood_config is not None
        else None
    )
    auto_return_config = parse_auto_return_config(auto_return)
    auto_return_scheduler = (
        AutoReturnScheduler(auto_return_config)
        if auto_return_config is not None
        else None
    )
    stale_cache = (
        StaleReadCache(
            include_params=include_params,
            max_intervention_rows=max_intervention_rows,
        )
        if probabilities.get("OLD_BONE", 0) > 0
        else None
    )
    adapter = _adapter_for(connection)
    stats = StatsTracker()
    proxy_class = SQLiteProxy if isinstance(adapter, SQLiteAdapter) else DuckDBProxy
    return proxy_class(
        connection,
        adapter,
        allow_native_passthrough=allow_native_passthrough,
        seed=seed,
        session_id=session_id,
        include_params=include_params,
        policy=FaultPolicy(
            probabilities=probabilities,
            stash_mode=stash_mode,
            tail_chase_mode=tail_chase_mode,
            on_max_rows=on_max_rows,
            chew_profiles=tuple(chew_profiles),
            wrong_count_max_delta=wrong_count_max_delta,
            sloth_max_delay_ms=sloth_max_delay_ms,
        ),
        log_path=log_path,
        max_intervention_rows=max_intervention_rows,
        house_limit=house_limit,
        only_tables=_normalize_tables(only_tables),
        exclude_tables=_normalize_tables(exclude_tables),
        debug=debug,
        clock=clock,
        mood=mood_engine,
        auto_return=auto_return_scheduler,
        stale_cache=stale_cache,
        stats=stats,
    )


def _normalize_tables(tables: Sequence[str] | None) -> frozenset[str] | None:
    if tables is None:
        return None
    normalized = frozenset(table.strip().lower() for table in tables)
    if not all(normalized):
        raise ValueError("table scope names must not be empty")
    return normalized


def connect(
    path: str = ":memory:",
    *,
    backend: str = "duckdb",
    seed: object,
    **options: Any,
) -> DuckDBProxy | SQLiteProxy:
    if backend == "sqlite":
        import sqlite3

        connection = sqlite3.connect(path)
    elif backend == "duckdb":
        import duckdb

        connection = duckdb.connect(path)
    else:
        raise ValueError("backend must be 'duckdb' or 'sqlite'")
    return wrap(connection, seed=seed, **options)
