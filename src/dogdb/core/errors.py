"""Machine-readable injected failures."""

from __future__ import annotations


class DogDBError(Exception):
    def __init__(
        self,
        message: str,
        *,
        event_id: str,
        fault: str,
        phase: str,
        retryable: bool,
        outcome: str,
    ) -> None:
        super().__init__(message)
        self.event_id = event_id
        self.fault = fault
        self.phase = phase
        self.retryable = retryable
        self.outcome = outcome


class DollyStashedError(DogDBError):
    pass


class DollyIgnoredError(DogDBError):
    pass


class DollyBarkError(DogDBError):
    pass


class DollyBusyError(DogDBError):
    pass


class DollyNoDropError(DogDBError):
    pass


class DollyTailChaseError(DogDBError):
    def __init__(
        self,
        message: str,
        *,
        event_id: str,
        fault: str,
        phase: str,
        retryable: bool,
        outcome: str,
        delivered_rows: int,
    ) -> None:
        super().__init__(
            message,
            event_id=event_id,
            fault=fault,
            phase=phase,
            retryable=retryable,
            outcome=outcome,
        )
        self.delivered_rows = delivered_rows
