"""Backend-neutral data structures used by DogDB core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LogicalResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    rowcount: int


@dataclass(frozen=True, slots=True)
class Decision:
    template_fingerprint: str
    parameter_fingerprint: str
    occurrence: int
    phase: str
    decision_key: str
