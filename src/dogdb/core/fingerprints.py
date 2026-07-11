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


def normalize_sql(sql: str) -> str:
    """Apply policy v1 normalization: trim, collapse whitespace, lowercase."""

    return _WHITESPACE.sub(" ", sql.strip()).lower()


def template_fingerprint(sql: str) -> str:
    value = hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()
    return f"sha256:{value}"


def _json_default(value: Any) -> dict[str, str]:
    value_type = type(value)
    qualified_name = f"{value_type.__module__}.{value_type.__qualname__}"
    if value_type not in (bytes, bytearray, date, time, datetime, Decimal, UUID):
        raise TypeError(
            f"unsupported parameter type {qualified_name}; only values with stable "
            "canonical text representations are accepted"
        )
    return {
        "type": qualified_name,
        "value": str(value),
    }


def parameter_fingerprint(params: Sequence[Any] | None, key: bytes) -> str:
    payload = json.dumps(
        list(params or ()),
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"
