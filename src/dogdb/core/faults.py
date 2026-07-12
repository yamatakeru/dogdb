"""Fault selection and LogicalResult transformations."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Callable

from dogdb.core.decision import DecisionEngine
from dogdb.core.errors import (
    DogDBError,
    DollyBarkError,
    DollyBusyError,
    DollyIgnoredError,
    DollyLimitError,
    DollyNoDropError,
    DollyStashedError,
    DollyTailChaseError,
)
from dogdb.core.event_log import Event, EventLog
from dogdb.core.house import HouseLedger, Treasure
from dogdb.core.models import Decision, LogicalResult
from dogdb.core.sql import SQLClassification, SQLKind
from dogdb.core.validation import require_positive_int

if TYPE_CHECKING:
    from dogdb.core.auto_return import AutoReturnScheduler
    from dogdb.core.mood import MoodEngine
    from dogdb.core.stale_cache import StaleEntry, StaleReadCache


KNOWN_FAULTS = frozenset(
    {
        "BARK",
        "GUARD_BOWL",
        "IGNORE",
        "SLOTH",
        "NO_DROP",
        "STASH",
        "FALSE_EMPTY",
        "TAIL_CHASE",
        "PAGE_HOLE",
        "ECHO",
        "SHUFFLE",
        "TANGLED_LEASH",
        "CHEW",
        "WRONG_COUNT",
        "OLD_BONE",
    }
)

BEFORE_EXECUTE_PRIORITY = ("BARK", "GUARD_BOWL", "IGNORE", "SLOTH")
ON_RESULT_PRIORITY = (
    "NO_DROP",
    "STASH_ERROR",
    "STASH",
    "FALSE_EMPTY",
    "TAIL_CHASE",
    "PAGE_HOLE",
    "ECHO",
    "SHUFFLE",
    "TANGLED_LEASH",
    "CHEW",
    "WRONG_COUNT",
    "OLD_BONE",
)
CHEW_PROFILES = ("utf8_truncate", "precision_loss", "nullify")
BEFORE_EXECUTE_ERRORS: dict[str, tuple[type[DogDBError], str]] = {
    "BARK": (DollyBarkError, "Dolly barked and blocked the request."),
    "GUARD_BOWL": (
        DollyBusyError,
        "Dolly is guarding the bowl; the database is busy.",
    ),
    "IGNORE": (DollyIgnoredError, "Dolly ignored the request and went back to sleep."),
}


@dataclass(slots=True)
class FaultPolicy:
    probabilities: dict[str, float] = field(default_factory=dict)
    stash_mode: str = "missing"
    tail_chase_mode: str = "silent"
    on_max_rows: str = "skip"
    chew_profiles: tuple[str, ...] = CHEW_PROFILES
    wrong_count_max_delta: int = 1
    sloth_max_delay_ms: int = 1_000

    def __post_init__(self) -> None:
        normalized = {
            str(name).upper(): value for name, value in self.probabilities.items()
        }
        unknown = set(normalized) - KNOWN_FAULTS
        if unknown:
            raise ValueError(f"unknown faults: {', '.join(sorted(unknown))}")
        for name, value in normalized.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} probability must be between 0 and 1")
        self.probabilities = {name: normalized.get(name, 0.0) for name in KNOWN_FAULTS}
        if self.stash_mode not in {"missing", "error"}:
            raise ValueError("stash_mode must be 'missing' or 'error'")
        if self.tail_chase_mode not in {"silent", "error"}:
            raise ValueError("tail_chase_mode must be 'silent' or 'error'")
        if self.on_max_rows not in {"skip", "error"}:
            raise ValueError("on_max_rows must be 'skip' or 'error'")
        unknown_profiles = set(self.chew_profiles) - set(CHEW_PROFILES)
        if unknown_profiles:
            raise ValueError(
                f"unknown CHEW profiles: {', '.join(sorted(unknown_profiles))}"
            )
        if not self.chew_profiles:
            raise ValueError("chew_profiles must not be empty")
        if len(set(self.chew_profiles)) != len(self.chew_profiles):
            raise ValueError("chew_profiles must not contain duplicates")
        self.wrong_count_max_delta = require_positive_int(
            self.wrong_count_max_delta, "wrong_count_max_delta"
        )
        self.sloth_max_delay_ms = require_positive_int(
            self.sloth_max_delay_ms, "sloth_max_delay_ms"
        )

    def probability(self, fault: str) -> float:
        return self.probabilities[fault.removesuffix("_ERROR")]

    @property
    def stash(self) -> float:
        return self.probability("STASH")

    @stash.setter
    def stash(self, value: float) -> None:
        self.probabilities["STASH"] = value

    @property
    def shuffle(self) -> float:
        return self.probability("SHUFFLE")

    @shuffle.setter
    def shuffle(self, value: float) -> None:
        self.probabilities["SHUFFLE"] = value

    @property
    def ignore(self) -> float:
        return self.probability("IGNORE")

    @ignore.setter
    def ignore(self, value: float) -> None:
        self.probabilities["IGNORE"] = value


class FaultEngine:
    def __init__(
        self,
        decisions: DecisionEngine,
        events: EventLog,
        house: HouseLedger,
        policy: FaultPolicy,
        max_intervention_rows: int,
        debug: bool = False,
        clock: Callable[[float], None] | None = None,
        mood: MoodEngine | None = None,
        auto_return: AutoReturnScheduler | None = None,
        stale_cache: StaleReadCache | None = None,
        intervention_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.decisions = decisions
        self.events = events
        self.house = house
        self.policy = policy
        self.max_intervention_rows = max_intervention_rows
        self.debug = debug
        self.clock = clock
        self.mood = mood
        self.auto_return = auto_return
        self.stale_cache = stale_cache
        self.intervention_callback = intervention_callback

    def _fires(self, decision: Decision, fault: str) -> bool:
        fault_name = fault.removesuffix("_ERROR")
        probability = self.policy.probability(fault_name)
        if self.mood is not None:
            probability *= self.mood.multiplier(fault_name)
        value = self.decisions.unit_interval(
            decision.decision_key, f"fire:{fault_name}"
        )
        return probability > 0 and (
            probability >= 1
            or value < probability
        )

    def select_candidate(
        self,
        decision: Decision,
        candidates: Iterable[str],
        *,
        phase: str,
    ) -> str | None:
        """Return the first firing eligible candidate in the contract order."""

        eligible = set(candidates)
        priority = (
            BEFORE_EXECUTE_PRIORITY if phase == "before_execute" else ON_RESULT_PRIORITY
        )
        return next(
            (fault for fault in priority if fault in eligible and self._fires(decision, fault)),
            None,
        )

    def _event(
        self,
        decision: Decision,
        *,
        fault: str,
        outcome: str,
        details: dict[str, object],
    ) -> Event:
        next_seq = self.events.next_seq()
        tag = f"event:{next_seq}:{fault}"
        event_id = self.decisions.deterministic_id(decision.decision_key, tag)
        event = self.events.append(
            event_id=event_id,
            event_type="fault_injected",
            fault=fault,
            phase=decision.phase,
            template_fingerprint=decision.template_fingerprint,
            parameter_fingerprint=decision.parameter_fingerprint,
            occurrence=decision.occurrence,
            decision_key=decision.decision_key,
            outcome=outcome,
            details=details,
        )
        if self.intervention_callback is not None:
            self.intervention_callback(decision.template_fingerprint)
        return event

    def before_execute(self, decision: Decision) -> bool:
        selected = self.select_candidate(
            decision,
            {"BARK", "GUARD_BOWL", "IGNORE", "SLOTH"},
            phase="before_execute",
        )
        if selected in BEFORE_EXECUTE_ERRORS:
            error_type, message = BEFORE_EXECUTE_ERRORS[selected]
            self._raise_before_execute(
                decision,
                fault=selected,
                error_type=error_type,
                message=message,
            )
        if selected == "SLOTH":
            delay_ms = 1 + self._derived_index(
                decision, "delay:SLOTH", self.policy.sloth_max_delay_ms
            )
            self._event(
                decision,
                fault="SLOTH",
                outcome="delayed",
                details={"delay_ms": delay_ms},
            )
            assert self.clock is not None
            self.clock(delay_ms / 1_000)
            return True
        self._debug_decision(
            decision,
            candidates=["BARK", "GUARD_BOWL", "IGNORE", "SLOTH"],
        )
        return False

    def _raise_before_execute(
        self,
        decision: Decision,
        *,
        fault: str,
        error_type: type[DogDBError],
        message: str,
    ) -> None:
        event = self._event(
            decision, fault=fault, outcome="not_executed", details={}
        )
        raise error_type(
            message,
            event_id=event.event_id,
            fault=fault,
            phase=decision.phase,
            retryable=True,
            outcome="not_executed",
        )

    def on_result(
        self,
        decision: Decision,
        classification: SQLClassification,
        result: LogicalResult,
    ) -> LogicalResult:
        if classification.kind is not SQLKind.SELECT:
            return result
        if len(result.rows) > self.max_intervention_rows:
            event = self._limit_exceeded(decision, observed=len(result.rows))
            if self.policy.on_max_rows == "error":
                raise DollyLimitError(
                    "Dolly cannot intervene in this materialized result; "
                    "increase max_intervention_rows to allow it.",
                    event_id=event.event_id,
                    fault=None,
                    phase=decision.phase,
                    retryable=False,
                    outcome="error",
                )
            return result

        if self.select_candidate(
            decision, {"NO_DROP"}, phase="on_result"
        ) == "NO_DROP":
            event = self._event(
                decision,
                fault="NO_DROP",
                outcome="response_lost",
                details={},
            )
            raise DollyNoDropError(
                "Dolly fetched the result but would not drop it.",
                event_id=event.event_id,
                fault="NO_DROP",
                phase=decision.phase,
                retryable=True,
                outcome="response_lost",
            )

        sticky = self.house.active_for(decision.template_fingerprint)
        if sticky:
            hidden = {treasure.row_index for treasure in sticky}
            rows = [row for index, row in enumerate(result.rows) if index not in hidden]
            if self.intervention_callback is not None:
                self.intervention_callback(decision.template_fingerprint)
            return LogicalResult(result.columns, rows, len(rows))

        candidates: list[str] = []
        chew_choice = (
            self._chew_choice(decision, result)
            if self.policy.probability("CHEW") > 0
            else None
        )
        stash_released = self.house.consume_release(decision.template_fingerprint)
        if not stash_released and result.rows:
            candidates.append(
                "STASH_ERROR" if self.policy.stash_mode == "error" else "STASH"
            )
        if classification.has_top_level_order_by is False and len(result.rows) > 1:
            candidates.append("SHUFFLE")
        if result.rows:
            candidates.extend(("FALSE_EMPTY", "TAIL_CHASE", "ECHO"))
        if (
            result.rows
            and classification.top_level_limit is not None
            and classification.top_level_offset is not None
            and classification.top_level_offset > 0
        ):
            candidates.append("PAGE_HOLE")
        if len(result.columns) > 1:
            candidates.append("TANGLED_LEASH")
        if chew_choice is not None:
            candidates.append("CHEW")
        candidates.append("WRONG_COUNT")
        stale_history = (
            self.stale_cache.history(decision)
            if self.stale_cache is not None
            else []
        )
        if stale_history:
            candidates.append("OLD_BONE")
        selected = self.select_candidate(decision, candidates, phase="on_result")

        if selected in {"STASH", "STASH_ERROR"}:
            return self._stash(decision, result, raises=self.policy.stash_mode == "error")
        if selected == "FALSE_EMPTY":
            return self._false_empty(decision, result)
        if selected == "TAIL_CHASE":
            return self._tail_chase(decision, result)
        if selected == "PAGE_HOLE":
            return self._page_hole(decision, result)
        if selected == "ECHO":
            return self._echo(decision, result)
        if selected == "SHUFFLE":
            return self._shuffle(decision, result)
        if selected == "TANGLED_LEASH":
            return self._tangled_leash(decision, result)
        if selected == "CHEW":
            assert chew_choice is not None
            return self._chew(decision, result, chew_choice)
        if selected == "WRONG_COUNT":
            return self._wrong_count(decision, result)
        if selected == "OLD_BONE":
            return self._old_bone(decision, stale_history)
        self._debug_decision(decision, candidates=candidates)
        return result

    def _debug_decision(
        self, decision: Decision, *, candidates: Iterable[str]
    ) -> Event | None:
        if not self.debug:
            return None
        next_seq = self.events.next_seq()
        return self.events.append(
            event_id=self.decisions.deterministic_id(
                decision.decision_key, f"event:{next_seq}:DECISION"
            ),
            event_type="decision_evaluated",
            phase=decision.phase,
            template_fingerprint=decision.template_fingerprint,
            parameter_fingerprint=decision.parameter_fingerprint,
            occurrence=decision.occurrence,
            decision_key=decision.decision_key,
            outcome="not_injected",
            details={"faults": list(candidates)},
        )

    def _limit_exceeded(self, decision: Decision, *, observed: int) -> Event:
        next_seq = self.events.next_seq()
        event_id = self.decisions.deterministic_id(
            decision.decision_key, f"event:{next_seq}:LIMIT"
        )
        return self.events.append(
            event_id=event_id,
            event_type="limit_exceeded",
            phase=decision.phase,
            template_fingerprint=decision.template_fingerprint,
            parameter_fingerprint=decision.parameter_fingerprint,
            occurrence=decision.occurrence,
            decision_key=decision.decision_key,
            outcome=(
                "error" if self.policy.on_max_rows == "error" else "fault_skipped"
            ),
            details={
                "limit": "max_intervention_rows",
                "configured": self.max_intervention_rows,
                "observed": observed,
            },
        )

    def _stash(
        self, decision: Decision, result: LogicalResult, *, raises: bool
    ) -> LogicalResult:
        row_index = self._derived_index(decision, "rows:STASH", len(result.rows))
        next_seq = self.events.next_seq()
        event_id = self.decisions.deterministic_id(
            decision.decision_key, f"event:{next_seq}:STASH"
        )
        treasure_id = self.decisions.deterministic_id(
            decision.decision_key, f"treasure:{row_index}"
        )
        treasure = Treasure(
            treasure_id,
            decision.template_fingerprint,
            row_index,
            result.rows[row_index],
            event_id,
            decision.parameter_fingerprint,
            decision.occurrence,
            decision.decision_key,
        )
        if not self.house.add(treasure):
            return result
        if self.auto_return is not None:
            self.auto_return.schedule(treasure.treasure_id, decision.decision_key)
        event = self._event(
            decision,
            fault="STASH",
            outcome="read_partial" if raises else "rows_hidden",
            details={"row_indices": [row_index], "treasure_id": treasure_id},
        )
        if raises:
            raise DollyStashedError(
                f"Dolly took row #{row_index} to her house.",
                event_id=event.event_id,
                fault="STASH",
                phase=decision.phase,
                retryable=True,
                outcome="read_partial",
            )
        rows = result.rows[:row_index] + result.rows[row_index + 1 :]
        return LogicalResult(result.columns, rows, len(rows))

    def _shuffle(self, decision: Decision, result: LogicalResult) -> LogicalResult:
        rows = list(result.rows)
        # Fisher-Yates with each swap derived directly from the decision key.
        for index in range(len(rows) - 1, 0, -1):
            value = self.decisions.unit_interval(
                decision.decision_key, f"perm:SHUFFLE:{index}"
            )
            swap = int(value * (index + 1))
            rows[index], rows[swap] = rows[swap], rows[index]
        if rows == result.rows:
            rows[0], rows[1] = rows[1], rows[0]
        self._event(decision, fault="SHUFFLE", outcome="rows_reordered", details={})
        return LogicalResult(result.columns, rows, len(rows))

    def _derived_index(self, decision: Decision, tag: str, size: int) -> int:
        digest = self.decisions.derive(decision.decision_key, tag)
        return int.from_bytes(digest[:8], "big") % size

    def _echo(self, decision: Decision, result: LogicalResult) -> LogicalResult:
        row_index = self._derived_index(decision, "rows:ECHO", len(result.rows))
        rows = list(result.rows)
        rows.insert(row_index + 1, rows[row_index])
        self._event(
            decision,
            fault="ECHO",
            outcome="rows_duplicated",
            details={"row_index": row_index},
        )
        return LogicalResult(list(result.columns), rows, len(rows))

    def _tail_chase(
        self, decision: Decision, result: LogicalResult
    ) -> LogicalResult:
        truncated = 1 + self._derived_index(
            decision, "rows:TAIL_CHASE", len(result.rows)
        )
        delivered = len(result.rows) - truncated
        event = self._event(
            decision,
            fault="TAIL_CHASE",
            outcome=(
                "read_partial"
                if self.policy.tail_chase_mode == "error"
                else "rows_truncated"
            ),
            details={"delivered_rows": delivered, "truncated_rows": truncated},
        )
        if self.policy.tail_chase_mode == "error":
            raise DollyTailChaseError(
                f"Dolly stopped the chase after delivering {delivered} rows.",
                event_id=event.event_id,
                fault="TAIL_CHASE",
                phase=decision.phase,
                retryable=True,
                outcome="read_partial",
                delivered_rows=delivered,
            )
        rows = result.rows[:delivered]
        return LogicalResult(list(result.columns), rows, len(rows))

    def _false_empty(
        self, decision: Decision, result: LogicalResult
    ) -> LogicalResult:
        self._event(
            decision,
            fault="FALSE_EMPTY",
            outcome="empty_result",
            details={},
        )
        return LogicalResult(list(result.columns), [], 0)

    def _page_hole(
        self, decision: Decision, result: LogicalResult
    ) -> LogicalResult:
        removed = 1 + self._derived_index(
            decision, "rows:PAGE_HOLE", len(result.rows)
        )
        rows = result.rows[removed:]
        self._event(
            decision,
            fault="PAGE_HOLE",
            outcome="page_hole",
            details={"rows_removed": removed},
        )
        return LogicalResult(list(result.columns), rows, len(rows))

    def _tangled_leash(
        self, decision: Decision, result: LogicalResult
    ) -> LogicalResult:
        left = self._derived_index(
            decision, "columns:TANGLED_LEASH", len(result.columns) - 1
        )
        columns = list(result.columns)
        columns[left], columns[left + 1] = columns[left + 1], columns[left]
        self._event(
            decision,
            fault="TANGLED_LEASH",
            outcome="column_labels_swapped",
            details={"column_indices": [left, left + 1]},
        )
        return LogicalResult(columns, list(result.rows), result.rowcount)

    def _chew_choice(
        self, decision: Decision, result: LogicalResult
    ) -> tuple[str, int, int, Any] | None:
        eligible: list[tuple[str, list[tuple[int, int, Any]]]] = []
        for profile in self.policy.chew_profiles:
            cells: list[tuple[int, int, Any]] = []
            for row_index, row in enumerate(result.rows):
                for column_index, value in enumerate(row):
                    mutated = _chew_value(profile, value)
                    if mutated is not _INELIGIBLE:
                        cells.append((row_index, column_index, mutated))
            if cells:
                eligible.append((profile, cells))
        if not eligible:
            return None
        profile_index = self._derived_index(
            decision, "profile:CHEW", len(eligible)
        )
        profile, cells = eligible[profile_index]
        cell_index = self._derived_index(decision, "cell:CHEW", len(cells))
        row_index, column_index, mutated = cells[cell_index]
        return profile, row_index, column_index, mutated

    def _chew(
        self,
        decision: Decision,
        result: LogicalResult,
        choice: tuple[str, int, int, Any],
    ) -> LogicalResult:
        profile, row_index, column_index, mutated = choice
        rows = list(result.rows)
        row = list(rows[row_index])
        row[column_index] = mutated
        rows[row_index] = tuple(row)
        self._event(
            decision,
            fault="CHEW",
            outcome="value_corrupted",
            details={
                "row_index": row_index,
                "column_index": column_index,
                "profile": profile,
            },
        )
        return LogicalResult(list(result.columns), rows, result.rowcount)

    def _wrong_count(
        self, decision: Decision, result: LogicalResult
    ) -> LogicalResult:
        actual = len(result.rows)
        derived = self.decisions.derive(decision.decision_key, "count:WRONG_COUNT")
        magnitude = (
            int.from_bytes(derived[1:9], "big") % self.policy.wrong_count_max_delta
        ) + 1
        delta = magnitude if actual == 0 or derived[0] % 2 == 0 else -magnitude
        reported = max(0, actual + delta)
        self._event(
            decision,
            fault="WRONG_COUNT",
            outcome="rowcount_misreported",
            details={
                "actual_rowcount": actual,
                "reported_rowcount": reported,
            },
        )
        return LogicalResult(list(result.columns), list(result.rows), reported)

    def _old_bone(
        self, decision: Decision, history: list[StaleEntry]
    ) -> LogicalResult:
        selected = history[
            self._derived_index(decision, "stale:OLD_BONE", len(history))
        ]
        self._event(
            decision,
            fault="OLD_BONE",
            outcome="stale_read",
            details={"stale_occurrence": selected.occurrence},
        )
        return LogicalResult(
            list(selected.result.columns),
            [tuple(row) for row in selected.result.rows],
            selected.result.rowcount,
        )


_INELIGIBLE = object()


def _chew_value(profile: str, value: Any) -> Any:
    if profile == "utf8_truncate":
        return value[:-1] if isinstance(value, str) and value else _INELIGIBLE
    if profile == "precision_loss":
        if isinstance(value, Decimal) and value.is_finite():
            try:
                rounded = value.quantize(Decimal(1))
            except InvalidOperation:
                return _INELIGIBLE
            return rounded if rounded != value else _INELIGIBLE
        if isinstance(value, float) and math.isfinite(value):
            rounded = float(round(value))
            return rounded if rounded != value else _INELIGIBLE
        return _INELIGIBLE
    if profile == "nullify":
        return None if value is not None else _INELIGIBLE
    raise AssertionError(f"unvalidated CHEW profile: {profile}")
