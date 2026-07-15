"""Anonymous SQL classification and intervention counters."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from sqlglot import __version__ as SQLGLOT_VERSION

from dogdb.core.sql import SQLKind

PASSTHROUGH_REASONS = frozenset(
    {
        "unsupported_parameter_type",
        "named_parameters",
        "unknown_sql",
        "transaction_statement",
        "executemany",
    }
)


@dataclass(slots=True)
class FingerprintStats:
    select: int = 0
    unknown: int = 0
    interventions: int = 0


class StatsTracker:
    def __init__(self) -> None:
        self._values: defaultdict[str, FingerprintStats] = defaultdict(
            FingerprintStats
        )
        self._escape_hatches = {"other": 0}
        self._passthrough: defaultdict[str, int] = defaultdict(int)

    def record_classification(self, fingerprint: str, kind: SQLKind) -> None:
        if kind is SQLKind.SELECT:
            self._values[fingerprint].select += 1
        elif kind is SQLKind.UNKNOWN:
            self._values[fingerprint].unknown += 1

    def record_intervention(self, fingerprint: str) -> None:
        self._values[fingerprint].interventions += 1

    def record_escape_hatch(self, name: str) -> None:
        self._escape_hatches[name] = self._escape_hatches.get(name, 0) + 1

    def record_passthrough(self, reason: str) -> None:
        if reason not in PASSTHROUGH_REASONS:
            raise ValueError(f"unknown passthrough reason: {reason!r}")
        self._passthrough[reason] += 1

    def snapshot(self) -> dict[str, object]:
        fingerprints = {
            fingerprint: asdict(value)
            for fingerprint, value in sorted(self._values.items())
        }
        return {
            "sqlglot_version": SQLGLOT_VERSION,
            "fingerprints": fingerprints,
            "escape_hatches": dict(self._escape_hatches),
            "passthrough": dict(sorted(self._passthrough.items())),
            "totals": {
                key: sum(value[key] for value in fingerprints.values())
                for key in ("select", "unknown", "interventions")
            },
        }
