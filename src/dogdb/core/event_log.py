"""Append-only schema-v2 JSONL event log with v1 read compatibility."""

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
    fault: str | None = None
    phase: str | None = None
    template_fingerprint: str | None = None
    parameter_fingerprint: str | None = None
    occurrence: int | None = None
    decision_key: str | None = None
    outcome: str | None = None
    details: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Event:
        if not isinstance(value, dict):
            raise ValueError("event must be a JSON object")
        version = value.get("schema_version")
        if version not in {1, 2}:
            raise ValueError(f"unsupported schema_version {version!r}")
        required = _required_fields(version, value.get("event_type"))
        missing = required - value.keys()
        if missing:
            raise ValueError(f"missing required fields: {', '.join(sorted(missing))}")
        return cls(
            **{
                field: value[field]
                for field in cls.__dataclass_fields__
                if field in value
            }
        )


_CORE_FIELDS = {"schema_version", "event_id", "session_id", "seq", "event_type"}
_V1_FIELDS = _CORE_FIELDS | {
    "fault",
    "phase",
    "template_fingerprint",
    "parameter_fingerprint",
    "occurrence",
    "decision_key",
    "outcome",
    "details",
}
_V2_FIELDS = {
    "fault_injected": _V1_FIELDS,
    "treasure_returned": _V1_FIELDS,
    "mood_changed": _CORE_FIELDS | {"details"},
    "limit_exceeded": _CORE_FIELDS
    | {
        "phase",
        "template_fingerprint",
        "parameter_fingerprint",
        "occurrence",
        "decision_key",
        "outcome",
        "details",
    },
    "decision_evaluated": _CORE_FIELDS
    | {
        "phase",
        "template_fingerprint",
        "parameter_fingerprint",
        "occurrence",
        "decision_key",
        "outcome",
        "details",
    },
}


def _required_fields(version: int, event_type: object) -> set[str]:
    if version == 1:
        return _V1_FIELDS
    try:
        return _V2_FIELDS[str(event_type)]
    except KeyError as error:
        raise ValueError(f"unknown schema-v2 event_type {event_type!r}") from error


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
            schema_version=2,
            session_id=self.session_id,
            seq=self._seq,
            **fields,
        )
        self._events.append(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                payload = {
                    key: value for key, value in asdict(event).items() if value is not None
                }
                stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
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
    with file_path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                events.append(Event.from_dict(json.loads(line.decode("utf-8"))))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                warnings.warn(
                    f"skipping corrupt DogDB event at line {line_number}: {error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
    return events
