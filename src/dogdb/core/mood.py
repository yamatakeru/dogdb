"""Deterministic logical-clock mood state machine."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dogdb.core.decision import POLICY_VERSION, DecisionEngine
from dogdb.core.faults import KNOWN_FAULTS
from dogdb.core.validation import require_positive_int


MOODS = ("CALM", "SLEEPY", "ZOOMY")
DEFAULT_MULTIPLIERS: dict[str, dict[str, float]] = {
    "CALM": {},
    "SLEEPY": {
        "IGNORE": 3.0,
        "SLOTH": 3.0,
        "NO_DROP": 3.0,
        "GUARD_BOWL": 3.0,
        "SHUFFLE": 0.5,
        "ECHO": 0.5,
        "TAIL_CHASE": 0.5,
    },
    "ZOOMY": {
        "SHUFFLE": 3.0,
        "ECHO": 3.0,
        "TAIL_CHASE": 3.0,
        "CHEW": 3.0,
        "IGNORE": 0.5,
        "SLOTH": 0.5,
    },
}


@dataclass(frozen=True, slots=True)
class MoodConfig:
    epoch_length: int
    multipliers: dict[str, dict[str, float]]


@dataclass(frozen=True, slots=True)
class MoodTransition:
    previous: str
    current: str
    tick: int
    epoch: int
    derivation_key: str


class MoodEngine:
    def __init__(
        self,
        *,
        seed: object,
        session_id: str,
        config: MoodConfig,
    ) -> None:
        self.tick = 0
        self.state = "CALM"
        self.config = config
        digest = hashlib.sha256(
            "\0".join((POLICY_VERSION, str(seed), session_id, "mood")).encode()
        ).hexdigest()
        self._derivation_key = f"sha256:{digest}"

    def advance(self) -> MoodTransition | None:
        self.tick += 1
        if self.tick % self.config.epoch_length:
            return None
        epoch = self.tick // self.config.epoch_length
        digest = DecisionEngine.derive(self._derivation_key, f"mood:{epoch}")
        current = MOODS[int.from_bytes(digest[:8], "big") % len(MOODS)]
        previous = self.state
        self.state = current
        if current == previous:
            return None
        return MoodTransition(
            previous=previous,
            current=current,
            tick=self.tick,
            epoch=epoch,
            derivation_key=f"sha256:{digest.hex()}",
        )

    def multiplier(self, fault: str) -> float:
        return self.config.multipliers[self.state].get(fault, 1.0)


def parse_mood_config(setting: bool | Mapping[str, Any] | None) -> MoodConfig | None:
    if setting is None or setting is False:
        return None
    if setting is True:
        value: Mapping[str, Any] = {}
    elif isinstance(setting, Mapping):
        value = setting
    else:
        raise ValueError("mood must be a boolean or mapping")

    unknown = set(value) - {"enabled", "epoch_length", "multipliers"}
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise ValueError(f"unknown mood settings: {names}")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("mood.enabled must be a boolean")
    if not enabled:
        return None

    epoch_length = value.get("epoch_length", 10)
    epoch_length = require_positive_int(epoch_length, "mood.epoch_length")

    multipliers = {
        state: {fault: float(multiplier) for fault, multiplier in defaults.items()}
        for state, defaults in DEFAULT_MULTIPLIERS.items()
    }
    overrides = value.get("multipliers", {})
    if not isinstance(overrides, Mapping):
        raise ValueError("mood.multipliers must be a mapping")
    for raw_state, raw_faults in overrides.items():
        state = str(raw_state).upper()
        if state not in MOODS:
            raise ValueError(f"unknown mood state: {raw_state}")
        if not isinstance(raw_faults, Mapping):
            raise ValueError(f"mood multipliers for {state} must be a mapping")
        for raw_fault, raw_multiplier in raw_faults.items():
            fault = str(raw_fault).upper()
            if fault not in KNOWN_FAULTS:
                raise ValueError(f"unknown fault in mood multipliers: {raw_fault}")
            if isinstance(raw_multiplier, bool) or not isinstance(
                raw_multiplier, (int, float)
            ):
                raise ValueError("mood multipliers must be finite non-negative numbers")
            multiplier = float(raw_multiplier)
            if not math.isfinite(multiplier) or multiplier < 0:
                raise ValueError("mood multipliers must be finite non-negative numbers")
            multipliers[state][fault] = multiplier

    return MoodConfig(epoch_length=epoch_length, multipliers=multipliers)
