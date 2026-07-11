"""Shared validation helpers for public configuration values."""

from __future__ import annotations


def require_positive_int(value: object, name: str) -> int:
    """Return *value* as an int, rejecting booleans and non-positive values."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
