"""API tests for Stage 5 S5.T1: job execution, artifacts, approve/reject locking, and corrections."""

from __future__ import annotations

from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings


def _maroochydore_geofence() -> dict[str, object]:
    return {
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


def test_s5_t1_end_to_end_job_run_artifacts_approve_reject_and_corrections(
    test_settings: Settings,
) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    proj = client.post("/api/projects", json={"area_name": "Maroochydore"}).json()
    project_id = proj["project_id"]
    rev = client.post(
        f"/api/projects/{project_id}/geofence",
        json=_maroochydore_geofence(),
    ).json()
    revision_id = rev["revision_id"]

    job_resp = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "geofence_revision": revision_id,
            "paper": "A4",
            "orientation": "landscape",
            "edition": "2026-10",
        },
    )
    assert job_resp.status_code == 201
    job_id = job_resp.json()["job_id"]

    # Run the job inline to proof_ready
    run_resp = client.post(f"/api/jobs/{job_id}/run")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "proof_ready"

    # Fetch all 5 governed artifacts
    for art_name in ("proof.pdf", "thumb.png", "qa-report.md", "qa-report.json", "manifest.json"):
        art_r = client.get(f"/api/jobs/{job_id}/artifacts/{art_name}")
        assert art_r.status_code == 200
        assert len(art_r.content) > 0

    # Reject without comment must return 422
    bad_rej = client.post(f"/api/jobs/{job_id}/reject", json={"reviewer": "qa_lead", "comment": "   "})
    assert bad_rej.status_code == 422

    # Approve locks job into finalized state with proof_sha256 in review_decisions
    app_r = client.post(
        f"/api/jobs/{job_id}/approve",
        json={"reviewer": "cartography_lead", "comment": "MCY proof approved for print"},
    )
    assert app_r.status_code == 200
    app_body = app_r.json()
    assert app_body["status"] == "finalized"
    assert len(app_body["proof_sha256"]) == 64

    # Attempting to reject or re-approve a finalized job returns 409
    dup_r = client.post(
        f"/api/jobs/{job_id}/reject",
        json={"reviewer": "qa_lead", "comment": "Too late"},
    )
    assert dup_r.status_code == 409

    # Submitting YAML corrections creates a new child job
    corr_yaml = "corrections:\n  - feature: road\n    osm_id: 9001\n    action: rename\n    name: 'Sunshine Motorway Tollway'\n"
    corr_r = client.post(
        f"/api/jobs/{job_id}/corrections",
        json={"yaml_content": corr_yaml, "author": "operator"},
    )
    assert corr_r.status_code == 201
    new_job_id = corr_r.json()["job_id"]
    assert new_job_id != job_id
