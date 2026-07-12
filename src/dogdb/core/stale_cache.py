"""Bounded in-memory cache of client-delivered logical results."""

from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass

from dogdb.core.models import Decision, LogicalResult


CacheKey = tuple[str, str | None]


@dataclass(frozen=True, slots=True)
class StaleEntry:
    key: CacheKey
    occurrence: int
    result: LogicalResult


class StaleReadCache:
    def __init__(
        self,
        *,
        include_params: bool,
        max_intervention_rows: int,
        per_fingerprint: int = 4,
        total_limit: int = 64,
    ) -> None:
        self.include_params = include_params
        self.max_intervention_rows = max_intervention_rows
        self.per_fingerprint = per_fingerprint
        self.total_limit = total_limit
        self._entries: OrderedDict[tuple[CacheKey, int], StaleEntry] = OrderedDict()
        self._by_key: defaultdict[CacheKey, deque[int]] = defaultdict(deque)

    def key_for(self, decision: Decision) -> CacheKey:
        parameter = decision.parameter_fingerprint if self.include_params else None
        return decision.template_fingerprint, parameter

    def history(self, decision: Decision) -> list[StaleEntry]:
        key = self.key_for(decision)
        occurrences = self._by_key.get(key)
        if occurrences is None:
            return []
        return [self._entries[(key, occurrence)] for occurrence in occurrences]

    def add(self, decision: Decision, result: LogicalResult) -> bool:
        if len(result.rows) > self.max_intervention_rows:
            return False
        key = self.key_for(decision)
        while len(self._by_key[key]) >= self.per_fingerprint:
            self._remove(key, self._by_key[key][0])
        entry = StaleEntry(
            key=key,
            occurrence=decision.occurrence,
            result=LogicalResult(
                list(result.columns),
                [tuple(row) for row in result.rows],
                result.rowcount,
            ),
        )
        self._entries[(key, decision.occurrence)] = entry
        self._by_key[key].append(decision.occurrence)
        while len(self._entries) > self.total_limit:
            oldest_key, oldest = next(iter(self._entries.items()))
            self._remove(oldest.key, oldest_key[1])
        return True

    def entries(self) -> list[StaleEntry]:
        return list(self._entries.values())

    def _remove(self, key: CacheKey, occurrence: int) -> None:
        self._entries.pop((key, occurrence), None)
        occurrences = self._by_key[key]
        try:
            occurrences.remove(occurrence)
        except ValueError:
            pass
        if not occurrences:
            self._by_key.pop(key, None)
