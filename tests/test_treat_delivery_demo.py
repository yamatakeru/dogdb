from __future__ import annotations

from examples.dollys_treat_delivery.app import create_app
from examples.dollys_treat_delivery.scenario import run_act


def test_happy_path_hides_the_implicit_ordering_bug():
    result = run_act("normal")

    assert result["passed"] is True
    assert result["product"] == "Bone Biscuit Refill"
    assert result["observed_status"] == "DELIVERED"
    assert result["faults"] == {}
    assert result["events"] == []
    assert "order by" not in str(result["sql"]).lower()


def test_dolly_shuffle_exposes_the_implicit_ordering_bug():
    result = run_act("dolly")

    assert result["passed"] is False
    assert result["expected_status"] == "DELIVERED"
    assert result["observed_status"] == "OUT_FOR_DELIVERY"
    assert result["faults"] == {"SHUFFLE": 1.0}
    assert [row["sequence"] for row in result["delivered_events"]] == [4, 1, 2, 3]
    assert result["events"] == [
        {
            "event_id": "6dcd9152aa96e269502db7b954277097",
            "fault": "SHUFFLE",
            "phase": "on_result",
            "occurrence": 1,
            "outcome": "rows_reordered",
            "category": "shape",
            "severity": "silent_corruption",
            "details": {},
        }
    ]


def test_ordered_query_resists_shuffle_without_disabling_it():
    result = run_act("fixed")

    assert result["passed"] is True
    assert result["observed_status"] == "DELIVERED"
    assert result["faults"] == {"SHUFFLE": 1.0}
    assert [row["sequence"] for row in result["delivered_events"]] == [1, 2, 3, 4]
    assert result["events"] == []
    assert str(result["sql"]).lower().endswith("order by sequence")


def test_dolly_shift_is_deterministic():
    assert run_act("dolly") == run_act("dolly")


def test_tutorial_routes_and_static_shell() -> None:
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        page = client.get("/")
        result = client.get("/api/acts/dolly.json")
        unknown = client.get("/api/acts/unknown.json")
        image = client.get("/assets/dolly.png")

    assert page.status_code == 200
    assert b"Dolly's First Shift" in page.data
    assert b'data-act="normal"' in page.data
    assert b'id="technical-report"' in page.data
    assert b'id="meta-faults"' in page.data
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    result_body = result.get_json()
    assert result_body["faults"] == {"SHUFFLE": 1.0}
    assert result_body["events"][0]["fault"] == "SHUFFLE"
    assert unknown.status_code == 404
    assert image.status_code == 200
    assert image.content_type == "image/png"
