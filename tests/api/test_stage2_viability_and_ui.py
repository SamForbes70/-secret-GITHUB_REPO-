"""API contract tests for Stage 2: /api/viability (S2.T2) and Geofence Editor UI (S2.T3)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings


def _make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        MAPS4U_DATA_DIR=tmp_path / "var",
        MAPS4U_QUEUE="inline",
        MAPS4U_ENV="test",
    )
    return TestClient(create_app(settings))


def test_post_viability_returns_assessment_for_valid_geofence(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    geofence = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.085, -26.660],
                [153.105, -26.660],
                [153.105, -26.645],
                [153.085, -26.645],
                [153.085, -26.660],
            ]
        ],
    }
    resp = client.post(
        "/api/viability",
        json={
            "geofence": geofence,
            "paper": "A4",
            "orientation": "landscape",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["viable"] is True
    assert body["scale_denominator"] > 0
    assert body["min_printed_mm"] >= 1.5
    assert "label_density_ratio" in body
    assert isinstance(body["warnings"], list)
    assert isinstance(body["choices"], list)


def test_post_viability_blocks_when_min_font_override_exceeds_style_font(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    geofence = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.085, -26.660],
                [153.105, -26.660],
                [153.105, -26.645],
                [153.085, -26.645],
                [153.085, -26.660],
            ]
        ],
    }
    resp = client.post(
        "/api/viability",
        json={
            "geofence": geofence,
            "paper": "A5",
            "orientation": "portrait",
            "min_font_override_mm": 2.5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["viable"] is False
    assert len(body["blockers"]) >= 1
    assert len(body["choices"]) == 4


def test_post_viability_rejects_self_intersecting_geometry_with_422(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    bowtie = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.085, -26.660],
                [153.105, -26.645],
                [153.105, -26.660],
                [153.085, -26.645],
                [153.085, -26.660],
            ]
        ],
    }
    resp = client.post(
        "/api/viability",
        json={
            "geofence": bowtie,
            "paper": "A4",
            "orientation": "landscape",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_GEO_INVALID"


def test_geofence_revisions_list_and_static_ui_served(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Static operator UI (S2.T3)
    ui_resp = client.get("/")
    assert ui_resp.status_code == 200
    assert "Maps4U" in ui_resp.text
    assert "/api/viability" in ui_resp.text or "app.js" in ui_resp.text

    js_resp = client.get("/static/app.js")
    assert js_resp.status_code == 200
    assert "/api/viability" in js_resp.text
    assert "/api/projects" in js_resp.text

    # Revision history list endpoint on project
    p_resp = client.post("/api/projects", json={"area_name": "Noosa Heads", "reference": "NOO-1"})
    assert p_resp.status_code == 201
    pid = p_resp.json()["project_id"]

    g1 = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.080, -26.398],
                [153.100, -26.398],
                [153.100, -26.383],
                [153.080, -26.383],
                [153.080, -26.398],
            ]
        ],
    }
    g2 = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.082, -26.397],
                [153.099, -26.397],
                [153.099, -26.384],
                [153.082, -26.384],
                [153.082, -26.397],
            ]
        ],
    }
    r1 = client.post(f"/api/projects/{pid}/geofence", json=g1)
    r2 = client.post(f"/api/projects/{pid}/geofence", json=g2)
    assert r1.status_code == 201 and r2.status_code == 201

    revs_resp = client.get(f"/api/projects/{pid}/revisions")
    assert revs_resp.status_code == 200
    revs = revs_resp.json()
    assert len(revs) == 2
    current_revs = [r for r in revs if r["is_current"]]
    assert len(current_revs) == 1
    assert current_revs[0]["revision_id"] == r2.json()["revision_id"]
