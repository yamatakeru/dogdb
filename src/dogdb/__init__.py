"""DogDB public API."""

from dogdb.proxy.connection import connect, wrap
from dogdb.core.errors import (
    DogDBError,
    DollyBarkError,
    DollyBusyError,
    DollyIgnoredError,
    DollyLimitError,
    DollyNoDropError,
    DollyPassthroughError,
    DollyPassthroughWarning,
    DollyStashedError,
    DollyTailChaseError,
)

__all__ = [
    "DogDBError",
    "DollyBarkError",
    "DollyBusyError",
    "DollyIgnoredError",
    "DollyLimitError",
    "DollyNoDropError",
    "DollyPassthroughError",
    "DollyPassthroughWarning",
    "DollyStashedError",
    "DollyTailChaseError",
    "connect",
    "wrap",
]
