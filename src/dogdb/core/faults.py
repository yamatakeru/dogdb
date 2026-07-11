"""Fault selection and LogicalResult transformations."""

from __future__ import annotations

from dataclasses import dataclass

from dogdb.core.decision import DecisionEngine
from dogdb.core.errors import DollyIgnoredError, DollyStashedError
from dogdb.core.event_log import Event, EventLog
from dogdb.core.house import HouseLedger, Treasure
from dogdb.core.models import Decision, LogicalResult
from dogdb.core.sql import SQLClassification, SQLKind


@dataclass(slots=True)
class FaultPolicy:
    stash: float = 0.0
    shuffle: float = 0.0
    ignore: float = 0.0
    stash_mode: str = "missing"

    def __post_init__(self) -> None:
        for name in ("stash", "shuffle", "ignore"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} probability must be between 0 and 1")
        if self.stash_mode not in {"missing", "error"}:
            raise ValueError("stash_mode must be 'missing' or 'error'")


class FaultEngine:
    def __init__(
        self,
        decisions: DecisionEngine,
        events: EventLog,
        house: HouseLedger,
        policy: FaultPolicy,
        max_rows: int,
    ) -> None:
        self.decisions = decisions
        self.events = events
        self.house = house
        self.policy = policy
        self.max_rows = max_rows

    def _fires(self, decision: Decision, fault: str, probability: float) -> bool:
        return probability > 0 and (
            probability >= 1
            or self.decisions.unit_interval(decision.decision_key, fault) < probability
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
        event_id = self.decisions.deterministic_id(
            decision.decision_key, f"event:{next_seq}:{fault}"
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
        if not self._fires(decision, "IGNORE", self.policy.ignore):
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
        if classification.kind is not SQLKind.SELECT or len(result.rows) > self.max_rows:
            return result

        sticky = self.house.active_for(decision.template_fingerprint)
        if sticky:
            hidden = {treasure.row_index for treasure in sticky}
            rows = [row for index, row in enumerate(result.rows) if index not in hidden]
            return LogicalResult(result.columns, rows, len(rows))

        stash_fires = not self.house.consume_release(
            decision.template_fingerprint
        ) and self._fires(decision, "STASH", self.policy.stash)
        shuffle_fires = (
            classification.has_top_level_order_by is False
            and self._fires(decision, "SHUFFLE", self.policy.shuffle)
        )

        # Failure injection outranks silent mutation.
        if stash_fires and self.policy.stash_mode == "error" and result.rows:
            return self._stash(decision, result, raises=True)
        if stash_fires and result.rows:
            return self._stash(decision, result, raises=False)
        if shuffle_fires and len(result.rows) > 1:
            return self._shuffle(decision, result)
        return result

    def _stash(
        self, decision: Decision, result: LogicalResult, *, raises: bool
    ) -> LogicalResult:
        digest = bytes.fromhex(decision.decision_key.removeprefix("sha256:"))
        row_index = int.from_bytes(digest[:8], "big") % len(result.rows)
        next_seq = len(self.events.events()) + 1
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
            value = self.decisions.unit_interval(decision.decision_key, f"SHUFFLE:{index}")
            swap = int(value * (index + 1))
            rows[index], rows[swap] = rows[swap], rows[index]
        if rows == result.rows:
            rows[0], rows[1] = rows[1], rows[0]
        self._event(decision, fault="SHUFFLE", outcome="rows_reordered", details={})
        return LogicalResult(result.columns, rows, len(rows))
