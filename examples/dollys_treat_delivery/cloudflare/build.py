"""Build Dolly's First Shift as a static Cloudflare deployment."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from examples.dollys_treat_delivery.scenario import ACTS, run_act


CLOUDFLARE_ROOT = Path(__file__).resolve().parent
DEMO_ROOT = CLOUDFLARE_ROOT.parent
REPOSITORY_ROOT = DEMO_ROOT.parents[1]


def main() -> None:
    _build_static_assets()


def _build_static_assets() -> None:
    destination = CLOUDFLARE_ROOT / "dist"
    acts_destination = destination / "api" / "acts"
    if destination.exists():
        shutil.rmtree(destination)
    (destination / "static").mkdir(parents=True)
    (destination / "assets").mkdir()
    acts_destination.mkdir(parents=True)

    template = (DEMO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    replacements = {
        "{{ url_for('static', filename='style.css') }}": "/static/style.css",
        "{{ url_for('static', filename='app.js') }}": "/static/app.js",
        "{{ url_for('dolly_image') }}": "/assets/dolly.png",
    }
    for source, target in replacements.items():
        template = template.replace(source, target)
    if "{{" in template or "}}" in template:
        raise ValueError("unresolved template expression in tutorial HTML")

    _ = (destination / "index.html").write_text(template, encoding="utf-8")
    _ = shutil.copy2(DEMO_ROOT / "static" / "style.css", destination / "static")
    _ = shutil.copy2(DEMO_ROOT / "static" / "app.js", destination / "static")
    _ = shutil.copy2(
        REPOSITORY_ROOT / "docs" / "assets" / "dolly.png",
        destination / "assets",
    )
    for act in sorted(ACTS):
        payload = json.dumps(run_act(act), indent=2, sort_keys=True) + "\n"
        _ = (acts_destination / f"{act}.json").write_text(
            payload,
            encoding="utf-8",
        )
    content_security_policy = " ".join(
        (
            "default-src 'self';",
            "img-src 'self';",
            "script-src 'self';",
            "style-src 'self';",
            "base-uri 'none';",
            "frame-ancestors 'none';",
            "form-action 'none'",
        )
    )
    headers = "\n".join(
        (
            "/api/acts/*",
            "  Cache-Control: no-store",
            "",
            "/*",
            "  X-Content-Type-Options: nosniff",
            "  Referrer-Policy: no-referrer",
            "  X-Frame-Options: DENY",
            f"  Content-Security-Policy: {content_security_policy}",
            "",
        )
    )
    _ = (destination / "_headers").write_text(
        headers,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
