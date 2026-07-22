"""Cloudflare Worker HTTP adapter for Dolly's First Shift."""

from __future__ import annotations

import json
import traceback
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint  # pyright: ignore[reportMissingImports]

from scenario import ACTS, run_act  # pyright: ignore[reportMissingImports]


API_PREFIX = "/api/acts/"
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Type": "text/plain; charset=utf-8",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if not path.startswith(API_PREFIX):
            return _response("Not Found", status=404)
        if request.method != "POST":
            return _response("Method Not Allowed", status=405, allow="POST")

        act = path.removeprefix(API_PREFIX)
        if "/" in act or act not in ACTS:
            return _response("Not Found", status=404)

        try:
            payload = run_act(act)
        except Exception:
            traceback.print_exc()
            return _response("Internal Server Error", status=500)

        headers = SECURITY_HEADERS | {"Content-Type": "application/json"}
        return Response(json.dumps(payload), status=200, headers=headers)


def _response(body: str, *, status: int, allow: str | None = None) -> Response:
    headers = SECURITY_HEADERS | ({"Allow": allow} if allow else {})
    return Response(body, status=status, headers=headers)
