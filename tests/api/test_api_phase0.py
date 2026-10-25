"""FastAPI route contract tests for Phase 0 / Stage 1 (S1.T5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from maps4u import __version__
from maps4u.api.main import create_app
from maps4u.core.config import Settings


def test_system_health_ready_and_meta(test_settings: Settings) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    r_health = client.get("/healthz")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ready = client.get("/readyz")
    assert r_ready.status_code == 200
    assert r_ready.json()["ready"] is True

    r_meta = client.get("/api/meta")
    assert r_meta.status_code == 200
    meta = r_meta.json()
    assert meta["version"] == __version__
    assert set(meta["papers"]) == {"A3", "A4", "A5"}
    assert set(meta["orientations"]) == {"landscape", "portrait"}
    assert meta["thresholds"]["min_font_mm"] == 1.5


def test_projects_and_geofence_revisions_lifecycle(test_settings: Settings) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    # Create project
    r_proj = client.post(
        "/api/projects",
        json={"area_name": "Maroochydore", "reference": "MCY-2026", "notes": "Pilot area"},
    )
    assert r_proj.status_code == 201
    project_id = r_proj.json()["project_id"]

    # Add valid geofence revision
    valid_poly = {
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
    r_geo1 = client.post(f"/api/projects/{project_id}/geofence", json=valid_poly)
    assert r_geo1.status_code == 201
    rev1 = r_geo1.json()["revision_id"]
    assert r_geo1.json()["is_current"] is True

    # Add a second edited geofence revision -> becomes current, first stays in history
    valid_poly_2 = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.086, -26.659],
                [153.104, -26.659],
                [153.104, -26.646],
                [153.086, -26.646],
                [153.086, -26.659],
            ]
        ],
    }
    r_geo2 = client.post(f"/api/projects/{project_id}/geofence", json=valid_poly_2)
    assert r_geo2.status_code == 201
    rev2 = r_geo2.json()["revision_id"]
    assert rev1 != rev2

    # Get project shows current geofence revision
    r_get = client.get(f"/api/projects/{project_id}")
    assert r_get.status_code == 200
    assert r_get.json()["current_geofence"]["revision_id"] == rev2

    # Create job freezing render specification
    r_job = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "geofence_revision": rev2,
            "paper": "A4",
            "orientation": "landscape",
            "edition": "ed1",
        },
    )
    assert r_job.status_code == 201
    job_data = r_job.json()
    assert job_data["project_id"] == project_id
    assert job_data["spec_id"] is not None


def test_illegal_geofence_rejected_with_error_code(test_settings: Settings) -> None:
    app = create_app(test_settings)
    client = TestClient(app)
    r_proj = client.post("/api/projects", json={"area_name": "BadGeo"}).json()
    pid = r_proj["project_id"]

    # Self-intersecting bowtie polygon -> 422 E_GEO_INVALID
    bowtie = {
        "type": "Polygon",
        "coordinates": [
            [
                [153.08, -26.66],
                [153.10, -26.64],
                [153.10, -26.66],
                [153.08, -26.64],
                [153.08, -26.66],
            ]
        ],
    }
    r_bad = client.post(f"/api/projects/{pid}/geofence", json=bowtie)
    assert r_bad.status_code == 422
    assert r_bad.json()["error"]["code"] == "E_GEO_INVALID"

    # Oversized polygon (> 600 km²) -> 422 E_GEO_TOO_LARGE
    huge = {
        "type": "Polygon",
        "coordinates": [
            [
                [152.0, -27.5],
                [154.0, -27.5],
                [154.0, -26.0],
                [152.0, -26.0],
                [152.0, -27.5],
            ]
        ],
    }
    r_huge = client.post(f"/api/projects/{pid}/geofence", json=huge)
    assert r_huge.status_code == 422
    assert r_huge.json()["error"]["code"] == "E_GEO_TOO_LARGE"
