"""Assemble the shared tutorial code and static assets for Wrangler."""

from __future__ import annotations

import shutil
from pathlib import Path


CLOUDFLARE_ROOT = Path(__file__).resolve().parent
DEMO_ROOT = CLOUDFLARE_ROOT.parent
REPOSITORY_ROOT = DEMO_ROOT.parents[1]


def main() -> None:
    _copy_runtime_modules()
    _build_static_assets()


def _copy_runtime_modules() -> None:
    shutil.copy2(DEMO_ROOT / "scenario.py", CLOUDFLARE_ROOT / "src" / "scenario.py")

    destination = CLOUDFLARE_ROOT / "python_modules" / "dogdb"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        REPOSITORY_ROOT / "src" / "dogdb",
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.py[co]"),
    )


def _build_static_assets() -> None:
    destination = CLOUDFLARE_ROOT / "dist"
    if destination.exists():
        shutil.rmtree(destination)
    (destination / "static").mkdir(parents=True)
    (destination / "assets").mkdir()

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

    (destination / "index.html").write_text(template, encoding="utf-8")
    shutil.copy2(DEMO_ROOT / "static" / "style.css", destination / "static")
    shutil.copy2(DEMO_ROOT / "static" / "app.js", destination / "static")
    shutil.copy2(
        REPOSITORY_ROOT / "docs" / "assets" / "dolly.png",
        destination / "assets",
    )
    (destination / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: no-referrer\n"
        "  X-Frame-Options: DENY\n"
        "  Content-Security-Policy: default-src 'self'; img-src 'self'; "
        "script-src 'self'; style-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
