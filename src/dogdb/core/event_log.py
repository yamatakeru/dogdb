"""Append-only schema-v1 JSONL event log."""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    schema_version: int
    event_id: str
    session_id: str
    seq: int
    event_type: str
    fault: str | None
    phase: str
    template_fingerprint: str
    parameter_fingerprint: str
    occurrence: int
    decision_key: str
    outcome: str
    details: dict[str, Any]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Event:
        return cls(**{field: value[field] for field in cls.__dataclass_fields__})


class EventLog:
    """A single-writer log. Cross-process concurrent appends are unsupported."""

    def __init__(self, session_id: str, path: str | Path | None = None) -> None:
        self.session_id = session_id
        self.path = Path(path) if path is not None else None
        self._events: list[Event] = []
        existing = read_events(self.path) if self.path is not None else []
        self._seq = max(
            (event.seq for event in existing if event.session_id == session_id),
            default=0,
        )

    def append(self, **fields: Any) -> Event:
        self._seq += 1
        event = Event(
            schema_version=1,
            session_id=self.session_id,
            seq=self._seq,
            **fields,
        )
        self._events.append(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")
        return event

    def events(self) -> list[Event]:
        if self.path is None:
            return list(self._events)
        return [
            event for event in read_events(self.path) if event.session_id == self.session_id
        ]


def read_events(path: str | Path) -> list[Event]:
    events: list[Event] = []
    file_path = Path(path)
    if not file_path.exists():
        return events
    with file_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                events.append(Event.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                warnings.warn(
                    f"skipping corrupt DogDB event at line {line_number}: {error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
    return events
