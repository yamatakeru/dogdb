"""Local-only web application for the interactive tutorial."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, send_file

from .scenario import ACTS, run_act

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOLLY_IMAGE = REPOSITORY_ROOT / "docs" / "assets" / "dolly.png"


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/acts/<act>.json")
    def execute_act(act: str) -> Response:
        if act not in ACTS:
            abort(404)

        response = jsonify(run_act(act))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/assets/dolly.png")
    def dolly_image() -> Response:
        return send_file(DOLLY_IMAGE, mimetype="image/png")

    return app


app = create_app()
