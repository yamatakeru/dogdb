from __future__ import annotations

import json

from examples.dollys_treat_delivery.cloudflare import build
from examples.dollys_treat_delivery.scenario import ACTS, run_act


def test_cloudflare_build_generates_static_demo(tmp_path, monkeypatch) -> None:
    cloudflare_root = tmp_path / "cloudflare"
    dist = cloudflare_root / "dist"
    acts_destination = dist / "api" / "acts"
    monkeypatch.setattr(build, "CLOUDFLARE_ROOT", cloudflare_root)

    build.main()

    index = (dist / "index.html").read_text()
    assert "{{" not in index
    assert 'href="/static/style.css"' in index
    assert 'src="/assets/dolly.png"' in index
    assert (dist / "static" / "app.js").is_file()
    assert (dist / "assets" / "dolly.png").is_file()
    for act in sorted(ACTS):
        trace = acts_destination / f"{act}.json"
        assert json.loads(trace.read_text()) == run_act(act)

    headers = (dist / "_headers").read_text()
    assert "/api/acts/*\n  Cache-Control: no-store" in headers
    assert "  X-Content-Type-Options: nosniff" in headers
    assert "  Referrer-Policy: no-referrer" in headers
    assert "  X-Frame-Options: DENY" in headers
    assert (
        "  Content-Security-Policy: default-src 'self'; img-src 'self'; "
        "script-src 'self'; style-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ) in headers
