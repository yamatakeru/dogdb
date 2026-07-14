"""Pure-key deterministic decision engine."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from dogdb.core.fingerprints import (
    parameter_fingerprint,
    template_fingerprint as fingerprint_template,
)
from dogdb.core.models import Decision


POLICY_VERSION = "dogdb-v4:normalize=trim+collapse-whitespace+lowercase-preserve-literals"


class _MemoizedParameterFingerprint:
    def __init__(self, supplier: Callable[[], str]) -> None:
        self._supplier = supplier
        self._value: str | None = None

    def __call__(self) -> str:
        if self._value is None:
            self._value = self._supplier()
        return self._value


class DecisionEngine:
    def __init__(
        self,
        *,
        seed: object,
        session_id: str,
        include_params: bool = False,
    ) -> None:
        self.seed = str(seed)
        self.session_id = session_id
        self.include_params = include_params
        self._occurrences: defaultdict[str, int] = defaultdict(int)
        self._hmac_key = hashlib.sha256(
            f"{POLICY_VERSION}\0{self.seed}\0{session_id}".encode()
        ).digest()

    def begin(
        self,
        sql: str,
        params: Sequence[Any] | None,
        *,
        template_fingerprint: str | None = None,
    ) -> tuple[str, _MemoizedParameterFingerprint, int]:
        template = (
            template_fingerprint
            if template_fingerprint is not None
            else fingerprint_template(sql)
        )
        self._occurrences[template] += 1
        parameter = _MemoizedParameterFingerprint(
            lambda: parameter_fingerprint(params, self._hmac_key)
        )
        return template, parameter, self._occurrences[template]

    def decide(
        self,
        *,
        template: str,
        parameter: str | Callable[[], str],
        occurrence: int,
        phase: str,
    ) -> Decision:
        parts = [
            POLICY_VERSION,
            self.seed,
            self.session_id,
            template,
            str(occurrence),
            phase,
        ]
        if self.include_params:
            parts.append(parameter() if callable(parameter) else parameter)
        digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
        return Decision(template, parameter, occurrence, phase, f"sha256:{digest}")

    @staticmethod
    def derive(decision_key: str, tag: str) -> bytes:
        """Derive bytes for one purpose using the contract separator."""

        return hashlib.sha256(f"{decision_key}:{tag}".encode("utf-8")).digest()

    @classmethod
    def unit_interval(cls, decision_key: str, tag: str) -> float:
        digest = cls.derive(decision_key, tag)
        return int.from_bytes(digest[:8], "big") / 2**64

    @classmethod
    def deterministic_id(cls, decision_key: str, tag: str) -> str:
        return cls.derive(decision_key, tag).hex()[:32]
