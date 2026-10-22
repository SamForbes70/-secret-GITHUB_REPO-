"""Automated backup and restore drill for Maps4U SQLite + governed artifact bundles (Stage 6 S6.T2)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings
from maps4u.core.db import run_migrations
from maps4u.core.ids import sha256_hex


def run_backup_restore_drill(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Create a live proof job, archive SQLite + artifacts, restore into clean dir, and verify SHA-256."""
    work_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    client = TestClient(app)

    proj = client.post("/api/projects", json={"area_name": "Backup Drill Area"}).json()
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
            "paper": "A4",
            "orientation": "landscape",
            "edition": "drill-2026-10",
        },
    ).json()
    job_id = job["job_id"]
    run_r = client.post(f"/api/jobs/{job_id}/run")
    assert run_r.status_code == 200

    orig_manifest = (settings.artifact_dir / job_id / "manifest.json").read_bytes()
    orig_pdf = (settings.artifact_dir / job_id / "proof.pdf").read_bytes()

    backup_staging = work_dir / "staging"
    backup_staging.mkdir(parents=True, exist_ok=True)
    db_backup_path = backup_staging / "maps4u.db"
    with sqlite3.connect(str(settings.db_path)) as src_conn, sqlite3.connect(
        str(db_backup_path)
    ) as dst_conn:
        src_conn.backup(dst_conn)

    shutil.copytree(settings.artifact_dir, backup_staging / "artifacts", dirs_exist_ok=True)
    archive_path = work_dir / "maps4u-backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(backup_staging, arcname="maps4u_backup")

    restore_dir = work_dir / "restored"
    restore_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(restore_dir, filter="data")

    restored_root = restore_dir / "maps4u_backup"
    restored_manifest = (restored_root / "artifacts" / job_id / "manifest.json").read_bytes()
    restored_pdf = (restored_root / "artifacts" / job_id / "proof.pdf").read_bytes()

    with sqlite3.connect(str(restored_root / "maps4u.db")) as r_conn:
        row = r_conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        db_ok = row is not None and row[0] == "proof_ready"

    manifest_match = sha256_hex(orig_manifest) == sha256_hex(restored_manifest)
    pdf_match = sha256_hex(orig_pdf) == sha256_hex(restored_pdf)
    return {
        "restored_ok": bool(db_ok and manifest_match and pdf_match),
        "job_id": job_id,
        "manifest_sha256_match": manifest_match,
        "pdf_sha256_match": pdf_match,
        "archive_path": str(archive_path),
    }


def main() -> None:
    fixture_path = next(
        (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "overpass").glob("*.json")
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        settings = Settings(
            maps4u_data_dir=base / "var",
            maps4u_db_path=base / "var" / "maps4u.db",
            maps4u_overpass_url=f"file://{fixture_path}",
            maps4u_env="test",
        )
        settings.ensure_dirs()
        run_migrations(settings.db_path)
        res = run_backup_restore_drill(settings, base / "drill")
        assert res["restored_ok"] is True
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
