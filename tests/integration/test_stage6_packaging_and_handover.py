"""Integration tests for Stage 6 (Gate G6): Docker packaging, handover docs, and UAT flow."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.bundle.archive import reproduce
from maps4u.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_s6_t1_docker_and_compose_packaging() -> None:
    dockerfile = REPO_ROOT / "Dockerfile"
    compose_file = REPO_ROOT / "docker-compose.yml"
    dockerignore = REPO_ROOT / ".dockerignore"

    assert dockerfile.is_file(), "Dockerfile must exist"
    assert compose_file.is_file(), "docker-compose.yml must exist"
    assert dockerignore.is_file(), ".dockerignore must exist"

    df_text = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:" in df_text
    assert "HEALTHCHECK" in df_text

    compose_data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = compose_data.get("services", {})
    assert {"api", "worker", "redis"}.issubset(set(services.keys()))
    assert "healthcheck" in services["api"]
    assert "volumes" in compose_data


def test_s6_t2_handover_docs_and_backup_restore_drill(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    required_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "runbook.md",
        REPO_ROOT / "docs" / "corrections-guide.md",
        REPO_ROOT / "docs" / "style-guide.md",
        REPO_ROOT / "docs" / "api.md",
        REPO_ROOT / "docs" / "deployment.md",
        REPO_ROOT / "docs" / "qa-acceptance.md",
    ]
    for doc_path in required_docs:
        assert doc_path.is_file(), f"Missing required handover doc: {doc_path}"
        assert len(doc_path.read_text(encoding="utf-8").strip()) > 200

    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.backup_restore_drill import run_backup_restore_drill

    drill = run_backup_restore_drill(test_settings, tmp_path / "drill")
    assert drill["restored_ok"] is True
    assert drill["manifest_sha256_match"] is True
    assert drill["pdf_sha256_match"] is True


def test_s6_t3_full_uat_operator_journey(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    # 1. Create project + geofence
    proj = client.post("/api/projects", json={"area_name": "Maroochydore UAT"}).json()
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
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=geofence).json()

    # 2. Assess viability
    viab = client.post(
        "/api/viability",
        json={"geofence": geofence, "paper": "A4", "orientation": "landscape"},
    )
    assert viab.status_code == 200
    assert viab.json()["viable"] is True

    # 3. Create initial job & render proof
    job1 = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "uat-2026-10",
        },
    ).json()
    job1_id = job1["job_id"]
    assert client.post(f"/api/jobs/{job1_id}/run").json()["status"] == "proof_ready"

    # 4. Reject initial proof with comment
    rej = client.post(
        f"/api/jobs/{job1_id}/reject",
        json={"reviewer": "client_reviewer", "comment": "Please rename First Avenue to First Ave Esplanade"},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"

    # 5. Submit YAML correction -> spawns child job2 -> run -> approve -> reproduce
    corr_yaml = (
        "corrections:\n"
        "  - feature: road\n"
        "    osm_id: 9002\n"
        "    action: rename\n"
        "    name: 'First Ave Esplanade'\n"
    )
    job2 = client.post(
        f"/api/jobs/{job1_id}/corrections",
        json={"yaml_content": corr_yaml, "author": "operator"},
    ).json()
    job2_id = job2["job_id"]
    assert client.post(f"/api/jobs/{job2_id}/run").json()["status"] == "proof_ready"

    app_r = client.post(
        f"/api/jobs/{job2_id}/approve",
        json={"reviewer": "client_reviewer", "comment": "Approved after street rename"},
    )
    assert app_r.status_code == 200
    assert app_r.json()["status"] == "finalized"

    repro = reproduce(job2_id, test_settings, tmp_path / "uat-repro")
    assert repro["matched"] is True
