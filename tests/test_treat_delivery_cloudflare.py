from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from examples.dollys_treat_delivery.cloudflare import build
from examples.dollys_treat_delivery.scenario import ACTS, run_act


WORKER_ENTRY = (
    Path(__file__).parents[1]
    / "examples"
    / "dollys_treat_delivery"
    / "cloudflare"
    / "src"
    / "entry.py"
)


def test_cloudflare_build_assembles_shared_sources(tmp_path, monkeypatch):
    cloudflare_root = tmp_path / "cloudflare"
    (cloudflare_root / "src").mkdir(parents=True)
    monkeypatch.setattr(build, "CLOUDFLARE_ROOT", cloudflare_root)

    build.main()

    index = (cloudflare_root / "dist" / "index.html").read_text()
    assert "{{" not in index
    assert 'href="/static/style.css"' in index
    assert 'src="/assets/dolly.png"' in index
    assert (cloudflare_root / "dist" / "static" / "app.js").is_file()
    assert (cloudflare_root / "dist" / "assets" / "dolly.png").is_file()
    assert (cloudflare_root / "src" / "scenario.py").is_file()
    assert (cloudflare_root / "python_modules" / "dogdb" / "__init__.py").is_file()
    assert not list((cloudflare_root / "python_modules" / "dogdb").rglob("*.pyc"))


def test_cloudflare_worker_routes_and_matches_scenario(monkeypatch):
    entry = _load_worker_entry(monkeypatch)

    result = _request(entry, "POST", "/api/acts/dolly")
    assert result.status == 200
    assert json.loads(result.body) == run_act("dolly")
    assert result.headers["Cache-Control"] == "no-store"

    wrong_method = _request(entry, "GET", "/api/acts/dolly")
    assert wrong_method.status == 405
    assert wrong_method.headers["Allow"] == "POST"

    assert _request(entry, "POST", "/api/acts/unknown").status == 404
    assert _request(entry, "POST", "/not-an-api-route").status == 404


def _load_worker_entry(monkeypatch):
    workers = ModuleType("workers")
    monkeypatch.setattr(workers, "Response", _Response, raising=False)
    monkeypatch.setattr(workers, "WorkerEntrypoint", object, raising=False)
    monkeypatch.setitem(sys.modules, "workers", workers)

    scenario = ModuleType("scenario")
    monkeypatch.setattr(scenario, "ACTS", ACTS, raising=False)
    monkeypatch.setattr(scenario, "run_act", run_act, raising=False)
    monkeypatch.setitem(sys.modules, "scenario", scenario)

    spec = importlib.util.spec_from_file_location("dogdb_cloudflare_entry", WORKER_ENTRY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(entry, method: str, path: str):
    request = SimpleNamespace(method=method, url=f"https://example.test{path}")
    return asyncio.run(entry.Default().fetch(request))


class _Response:
    def __init__(
        self,
        body: str,
        *,
        status: int,
        headers: dict[str, str],
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers
