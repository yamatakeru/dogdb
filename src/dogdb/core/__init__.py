"""Backend-independent fault injection engine."""

from dogdb.core.errors import DogDBError, DollyIgnoredError, DollyStashedError
from dogdb.core.house import rebuild_house
from dogdb.core.models import LogicalResult

__all__ = [
    "DogDBError",
    "DollyIgnoredError",
    "DollyStashedError",
    "LogicalResult",
    "rebuild_house",
]
