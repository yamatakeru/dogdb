"""Stable, language-portable fingerprints."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Sequence
from typing import Any


_WHITESPACE = re.compile(r"\s+")


def normalize_sql(sql: str) -> str:
    """Apply policy v1 normalization: trim, collapse whitespace, lowercase."""

    return _WHITESPACE.sub(" ", sql.strip()).lower()


def template_fingerprint(sql: str) -> str:
    value = hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()
    return f"sha256:{value}"


def _json_default(value: Any) -> dict[str, str]:
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
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
