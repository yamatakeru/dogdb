"""Stable, language-portable fingerprints."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


_WHITESPACE = re.compile(r"\s+")
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
    """Apply policy v4 normalization: trim, collapse whitespace, lowercase
    non-literal parts, preserve string literal case."""

    return _WHITESPACE.sub(" ", _lower_preserving_literals(sql.strip()))


def _lower_preserving_literals(text: str) -> str:
    """Lowercase characters outside single-quoted string literals."""
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "'":
            start = i
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
            result.append(text[start : i + 1 if i < n else i])
            i += 1 if i < n else 0
        else:
            result.append(text[i].lower())
            i += 1
    return "".join(result)


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
