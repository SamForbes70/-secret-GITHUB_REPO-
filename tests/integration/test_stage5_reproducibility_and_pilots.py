"""Integration tests for Stage 5 S5.T2 (reproduce determinism) and S5.T3 (3-pilot end-to-end runs)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.bundle.archive import reproduce
from maps4u.core.config import Settings

PILOT_AREAS = [
    ("Maroochydore", "A4", "landscape"),
    ("Noosa", "A3", "landscape"),
    ("Bribie Island - Sandstone Point", "A4", "portrait"),
]


@pytest.mark.parametrize(("area_name", "paper", "orientation"), PILOT_AREAS)
def test_s5_t2_and_t3_pilot_runs_and_reproducibility(
    test_settings: Settings,
    tmp_path: Path,
    area_name: str,
    paper: str,
    orientation: str,
) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    proj = client.post("/api/projects", json={"area_name": area_name}).json()
    rev = client.post(
        f"/api/projects/{proj['project_id']}/geofence",
        json={
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
        },
    ).json()
    job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": paper,
            "orientation": orientation,
            "edition": "pilot-2026-10",
        },
    ).json()
    job_id = job["job_id"]

    run_r = client.post(f"/api/jobs/{job_id}/run")
    assert run_r.status_code == 200
    assert run_r.json()["status"] == "proof_ready"

    repro = reproduce(job_id=job_id, settings=test_settings, out_dir=tmp_path / f"repro-{job_id}")
    assert repro["matched"] is True
    assert repro["original_content_hash"] == repro["reproduced_content_hash"]
    assert repro["original_pdf_sha256"] == repro["reproduced_pdf_sha256"]
