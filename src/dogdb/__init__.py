"""DogDB public API."""

from dogdb.proxy.connection import connect, wrap
from dogdb.core.errors import (
    DogDBError,
    DollyBarkError,
    DollyBusyError,
    DollyIgnoredError,
    DollyNoDropError,
    DollyStashedError,
    DollyTailChaseError,
)

__all__ = [
    "DogDBError",
    "DollyBarkError",
    "DollyBusyError",
    "DollyIgnoredError",
    "DollyNoDropError",
    "DollyStashedError",
    "DollyTailChaseError",
    "connect",
    "wrap",
]
