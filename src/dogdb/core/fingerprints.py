"""Stable, language-portable fingerprints."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


FINGERPRINT_PARAMETER_TYPES = (
    type(None),
    bool,
    int,
    float,
    str,
    bytes,
    bytearray,
    date,
    time,
    datetime,
    Decimal,
    UUID,
)


def normalize_sql(sql: str) -> str:
    """Apply policy v4 normalization in one left-to-right scan."""

    normalized: list[str] = []
    pending_space = False
    in_literal = False
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if in_literal:
            normalized.append(char)
            if char == "'":
                if next_char == "'":
                    normalized.append(next_char)
                    index += 2
                    continue
                in_literal = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            pending_space = bool(normalized)
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index < len(sql):
                if sql[index] == "*" and index + 1 < len(sql) and sql[index + 1] == "/":
                    index += 2
                    break
                index += 1
            pending_space = bool(normalized)
            continue
        if char.isspace():
            pending_space = bool(normalized)
            index += 1
            continue

        if pending_space:
            normalized.append(" ")
            pending_space = False
        if char == "'":
            in_literal = True
            normalized.append(char)
        else:
            normalized.append(char.lower())
        index += 1

    return "".join(normalized)


def template_fingerprint(sql: str) -> str:
    value = hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()
    return f"sha256:{value}"


def _unsupported_parameter_type(value: Any) -> TypeError:
    value_type = type(value)
    qualified_name = f"{value_type.__module__}.{value_type.__qualname__}"
    return TypeError(
        f"unsupported parameter type {qualified_name}; only values with stable "
        "canonical text representations are accepted"
    )


def _json_default(value: Any) -> dict[str, str]:
    value_type = type(value)
    if value_type not in FINGERPRINT_PARAMETER_TYPES:
        raise _unsupported_parameter_type(value)
    qualified_name = f"{value_type.__module__}.{value_type.__qualname__}"
    return {
        "type": qualified_name,
        "value": str(value),
    }


def params_in_fingerprint_domain(params: Sequence[Any] | None) -> bool:
    """Return whether every parameter has a stable fingerprint representation."""

    values = () if params is None else params
    return all(type(value) in FINGERPRINT_PARAMETER_TYPES for value in values)


def parameter_fingerprint(params: Sequence[Any] | None, key: bytes) -> str:
    values = () if params is None else params
    if not params_in_fingerprint_domain(values):
        unsupported = next(
            value
            for value in values
            if type(value) not in FINGERPRINT_PARAMETER_TYPES
        )
        raise _unsupported_parameter_type(unsupported)
    payload = json.dumps(
        list(values),
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"
