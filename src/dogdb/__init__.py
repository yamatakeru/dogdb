"""DogDB public API."""

from dogdb.proxy.connection import connect, wrap
from dogdb.core.errors import DogDBError, DollyIgnoredError, DollyStashedError

__all__ = [
    "DogDBError",
    "DollyIgnoredError",
    "DollyStashedError",
    "connect",
    "wrap",
]
