"""DogDB public API."""

from dogdb.proxy.connection import connect, wrap
from dogdb.core.errors import (
    DogDBError,
    DollyIgnoredError,
    DollyStashedError,
    DollyTailChaseError,
)

__all__ = [
    "DogDBError",
    "DollyIgnoredError",
    "DollyStashedError",
    "DollyTailChaseError",
    "connect",
    "wrap",
]
