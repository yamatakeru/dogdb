"""In-memory Dog House ledger and event projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from dogdb.core.event_log import Event


@dataclass(frozen=True, slots=True)
class Treasure:
    treasure_id: str
    template_fingerprint: str
    row_index: int
    row: tuple[Any, ...]
    event_id: str
    parameter_fingerprint: str
    occurrence: int
    decision_key: str


@dataclass(frozen=True, slots=True)
class ProjectedTreasure:
    treasure_id: str
    template_fingerprint: str
    row_index: int
    event_id: str


class HouseLedger:
    def __init__(self, capacity: int = 1_000) -> None:
        self.capacity = capacity
        self._treasures: dict[str, Treasure] = {}
        self._by_location: dict[tuple[str, int], str] = {}
        self._released_templates: set[str] = set()

    def add(self, treasure: Treasure) -> bool:
        location = (treasure.template_fingerprint, treasure.row_index)
        if location in self._by_location or len(self._treasures) >= self.capacity:
            return False
        self._treasures[treasure.treasure_id] = treasure
        self._by_location[location] = treasure.treasure_id
        return True

    def active_for(self, template: str) -> list[Treasure]:
        return sorted(
            (t for t in self._treasures.values() if t.template_fingerprint == template),
            key=lambda treasure: treasure.row_index,
        )

    def values(self) -> list[Treasure]:
        return list(self._treasures.values())

    def return_treasure(self, treasure_id: str) -> Treasure | None:
        treasure = self._treasures.pop(treasure_id, None)
        if treasure is not None:
            self._by_location.pop((treasure.template_fingerprint, treasure.row_index), None)
            self._released_templates.add(treasure.template_fingerprint)
        return treasure

    def return_all(self) -> list[Treasure]:
        returned = list(self._treasures.values())
        for treasure in returned:
            self._released_templates.add(treasure.template_fingerprint)
        self._treasures.clear()
        self._by_location.clear()
        return returned

    def consume_release(self, template: str) -> bool:
        if template not in self._released_templates:
            return False
        self._released_templates.remove(template)
        return True


def rebuild_house(events: Iterable[Event]) -> list[ProjectedTreasure]:
    active: dict[str, ProjectedTreasure] = {}
    for event in events:
        if event.event_type == "fault_injected" and event.fault == "STASH":
            treasure_id = event.details.get("treasure_id")
            indices = event.details.get("row_indices", [])
            if treasure_id and indices:
                active[treasure_id] = ProjectedTreasure(
                    treasure_id=treasure_id,
                    template_fingerprint=event.template_fingerprint,
                    row_index=indices[0],
                    event_id=event.event_id,
                )
        elif event.event_type == "treasure_returned":
            active.pop(event.details.get("treasure_id"), None)
    return list(active.values())
