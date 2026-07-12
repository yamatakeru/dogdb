"""Backend-neutral data structures used by DogDB core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LogicalResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    rowcount: int


class Decision:
    __slots__ = (
        "template_fingerprint",
        "_parameter_fingerprint",
        "occurrence",
        "phase",
        "decision_key",
    )

    def __init__(
        self,
        template_fingerprint: str,
        parameter_fingerprint: str | Callable[[], str],
        occurrence: int,
        phase: str,
        decision_key: str,
    ) -> None:
        self.template_fingerprint = template_fingerprint
        self._parameter_fingerprint = parameter_fingerprint
        self.occurrence = occurrence
        self.phase = phase
        self.decision_key = decision_key

    @property
    def parameter_fingerprint(self) -> str:
        value = self._parameter_fingerprint
        return value() if callable(value) else value
