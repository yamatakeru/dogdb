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
    column_types: list[Any] | None = None


class Decision:
    """Frozen value object; the parameter fingerprint may resolve lazily."""

    template_fingerprint: str
    _parameter_fingerprint: str | Callable[[], str]
    occurrence: int
    phase: str
    decision_key: str

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
        object.__setattr__(self, "template_fingerprint", template_fingerprint)
        object.__setattr__(self, "_parameter_fingerprint", parameter_fingerprint)
        object.__setattr__(self, "occurrence", occurrence)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "decision_key", decision_key)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"Decision is frozen; cannot assign {name!r}")

    @property
    def parameter_fingerprint(self) -> str:
        value = self._parameter_fingerprint
        if callable(value):
            value = value()
            object.__setattr__(self, "_parameter_fingerprint", value)
        return value

    def _astuple(self) -> tuple[str, str, int, str, str]:
        return (
            self.template_fingerprint,
            self.parameter_fingerprint,
            self.occurrence,
            self.phase,
            self.decision_key,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self._astuple() == other._astuple()

    def __hash__(self) -> int:
        return hash(self._astuple())

    def __repr__(self) -> str:
        return (
            f"Decision(template_fingerprint={self.template_fingerprint!r}, "
            f"parameter_fingerprint={self.parameter_fingerprint!r}, "
            f"occurrence={self.occurrence!r}, phase={self.phase!r}, "
            f"decision_key={self.decision_key!r})"
        )
