"""Logical-clock scheduling for automatic treasure returns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dogdb.core.decision import DecisionEngine


@dataclass(frozen=True, slots=True)
class AutoReturnConfig:
    min_operations: int = 1
    max_operations: int = 10


class AutoReturnScheduler:
    def __init__(self, config: AutoReturnConfig) -> None:
        self.config = config
        self.current_tick = 0
        self._next_order = 0
        self._scheduled: dict[str, tuple[int, int]] = {}

    def advance(self, tick: int) -> list[str]:
        self.current_tick = tick
        due = sorted(
            (
                (due_tick, order, treasure_id)
                for treasure_id, (due_tick, order) in self._scheduled.items()
                if due_tick <= tick
            )
        )
        for _, _, treasure_id in due:
            self._scheduled.pop(treasure_id, None)
        return [treasure_id for _, _, treasure_id in due]

    def schedule(self, treasure_id: str, decision_key: str) -> int:
        span = self.config.max_operations - self.config.min_operations + 1
        digest = DecisionEngine.derive(decision_key, "hold:RETURN")
        hold = self.config.min_operations + int.from_bytes(digest[:8], "big") % span
        self._next_order += 1
        self._scheduled[treasure_id] = (
            self.current_tick + hold,
            self._next_order,
        )
        return hold

    def cancel(self, treasure_id: str) -> None:
        self._scheduled.pop(treasure_id, None)


def parse_auto_return_config(
    setting: bool | Mapping[str, Any] | Sequence[int] | None,
) -> AutoReturnConfig | None:
    if setting is None or setting is False:
        return None
    if setting is True:
        minimum, maximum = 1, 10
    elif isinstance(setting, Mapping):
        unknown = set(setting) - {"enabled", "min_operations", "max_operations"}
        if unknown:
            names = ", ".join(sorted(str(item) for item in unknown))
            raise ValueError(f"unknown auto_return settings: {names}")
        enabled = setting.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("auto_return.enabled must be a boolean")
        if not enabled:
            return None
        minimum = setting.get("min_operations", 1)
        maximum = setting.get("max_operations", 10)
    elif isinstance(setting, Sequence) and not isinstance(setting, (str, bytes)):
        if len(setting) != 2:
            raise ValueError("auto_return range must contain exactly two integers")
        minimum, maximum = setting
    else:
        raise ValueError("auto_return must be a boolean, mapping, or two-item range")

    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (minimum, maximum)
    ):
        raise ValueError("auto_return bounds must be positive integers")
    if minimum > maximum:
        raise ValueError("auto_return minimum must not exceed maximum")
    return AutoReturnConfig(minimum, maximum)
