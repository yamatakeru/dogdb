"""Fault selection and LogicalResult transformations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from dogdb.core.decision import DecisionEngine
from dogdb.core.errors import DollyIgnoredError, DollyStashedError
from dogdb.core.event_log import Event, EventLog
from dogdb.core.house import HouseLedger, Treasure
from dogdb.core.models import Decision, LogicalResult
from dogdb.core.sql import SQLClassification, SQLKind


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


@dataclass(slots=True)
class FaultPolicy:
    probabilities: dict[str, float] = field(default_factory=dict)
    stash_mode: str = "missing"

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
        max_rows: int,
        debug: bool = False,
    ) -> None:
        self.decisions = decisions
        self.events = events
        self.house = house
        self.policy = policy
        self.max_rows = max_rows
        self.debug = debug

    def _fires(self, decision: Decision, fault: str) -> bool:
        fault_name = fault.removesuffix("_ERROR")
        probability = self.policy.probability(fault_name)
        if fault_name in {"STASH", "SHUFFLE", "IGNORE"}:
            value = self.decisions.legacy_unit_interval(
                decision.decision_key, fault_name
            )
        else:
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
        next_seq = len(self.events.events()) + 1
        tag = f"event:{next_seq}:{fault}"
        event_id = (
            self.decisions.legacy_id(decision.decision_key, tag)
            if fault in {"STASH", "SHUFFLE", "IGNORE"}
            else self.decisions.deterministic_id(decision.decision_key, tag)
        )
        return self.events.append(
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

    def before_execute(self, decision: Decision) -> None:
        selected = self.select_candidate(
            decision, {"IGNORE"}, phase="before_execute"
        )
        if selected != "IGNORE":
            self._debug_decision(decision, candidates=["IGNORE"])
            return
        event = self._event(
            decision, fault="IGNORE", outcome="not_executed", details={}
        )
        raise DollyIgnoredError(
            "Dolly ignored the request and went back to sleep.",
            event_id=event.event_id,
            fault="IGNORE",
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
        if len(result.rows) > self.max_rows:
            self._limit_exceeded(decision, observed=len(result.rows))
            return result

        sticky = self.house.active_for(decision.template_fingerprint)
        if sticky:
            hidden = {treasure.row_index for treasure in sticky}
            rows = [row for index, row in enumerate(result.rows) if index not in hidden]
            return LogicalResult(result.columns, rows, len(rows))

        candidates: list[str] = []
        stash_released = self.house.consume_release(decision.template_fingerprint)
        if not stash_released and result.rows:
            candidates.append(
                "STASH_ERROR" if self.policy.stash_mode == "error" else "STASH"
            )
        if classification.has_top_level_order_by is False and len(result.rows) > 1:
            candidates.append("SHUFFLE")
        selected = self.select_candidate(decision, candidates, phase="on_result")

        if selected in {"STASH", "STASH_ERROR"}:
            return self._stash(decision, result, raises=self.policy.stash_mode == "error")
        if selected == "SHUFFLE":
            return self._shuffle(decision, result)
        self._debug_decision(decision, candidates=candidates)
        return result

    def _debug_decision(
        self, decision: Decision, *, candidates: Iterable[str]
    ) -> Event | None:
        if not self.debug:
            return None
        next_seq = len(self.events.events()) + 1
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
        next_seq = len(self.events.events()) + 1
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
            outcome="fault_skipped",
            details={
                "limit": "max_rows",
                "configured": self.max_rows,
                "observed": observed,
            },
        )

    def _stash(
        self, decision: Decision, result: LogicalResult, *, raises: bool
    ) -> LogicalResult:
        digest = bytes.fromhex(decision.decision_key.removeprefix("sha256:"))
        row_index = int.from_bytes(digest[:8], "big") % len(result.rows)
        next_seq = len(self.events.events()) + 1
        event_id = self.decisions.legacy_id(
            decision.decision_key, f"event:{next_seq}:STASH"
        )
        treasure_id = self.decisions.legacy_id(
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
            value = self.decisions.legacy_unit_interval(
                decision.decision_key, f"SHUFFLE:{index}"
            )
            swap = int(value * (index + 1))
            rows[index], rows[swap] = rows[swap], rows[index]
        if rows == result.rows:
            rows[0], rows[1] = rows[1], rows[0]
        self._event(decision, fault="SHUFFLE", outcome="rows_reordered", details={})
        return LogicalResult(result.columns, rows, len(rows))
