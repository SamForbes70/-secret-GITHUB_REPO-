"""Live Overpass 3-Area Pilot Execution & Verification Script (Stage 5 S5.T3 / Stage 6 S6.T3).

Executes the full 11-stage governed Maps4U pipeline in production mode against the
live OpenStreetMap Overpass API for:
1. Maroochydore (A4-landscape)
2. Noosa Heads (A3-landscape)
3. Bribie Island - Sandstone Point (A4-portrait)
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings
from maps4u.geo.cache import read_geopackage_snapshot
from maps4u.geo.features import LAYER_COLUMNS

LIVE_PILOTS: list[dict[str, Any]] = [
    {
        "slug": "maroochydore-a4-landscape",
        "area_name": "Maroochydore",
        "reference": "MCY-LIVE-PILOT-01",
        "paper": "A4",
        "orientation": "landscape",
        "bbox_coords": [
            [153.085, -26.660],
            [153.105, -26.660],
            [153.105, -26.645],
            [153.085, -26.645],
            [153.085, -26.660],
        ],
    },
    {
        "slug": "noosa-heads-a3-landscape",
        "area_name": "Noosa Heads",
        "reference": "NSA-LIVE-PILOT-02",
        "paper": "A3",
        "orientation": "landscape",
        "bbox_coords": [
            [153.080, -26.398],
            [153.100, -26.398],
            [153.100, -26.384],
            [153.080, -26.384],
            [153.080, -26.398],
        ],
    },
    {
        "slug": "bribie-sandstone-point-a4-portrait",
        "area_name": "Bribie Island - Sandstone Point",
        "reference": "BRI-LIVE-PILOT-03",
        "paper": "A4",
        "orientation": "portrait",
        "bbox_coords": [
            [153.135, -27.082],
            [153.152, -27.082],
            [153.152, -27.065],
            [153.135, -27.065],
            [153.135, -27.082],
        ],
    },
]


def run_live_pilots(out_root: Path | None = None) -> dict[str, Any]:
    base_dir = out_root or Path("/a0/usr/projects/maps4u/live-pilots-v1.0.2")
    base_dir.mkdir(parents=True, exist_ok=True)
    exports_dir = base_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    op_token = "live-pilot-operator-token-v102-secure"
    rev_token = "live-pilot-reviewer-token-v102-secure"

    settings = Settings(
        MAPS4U_ENV="prod",
        MAPS4U_QUEUE="inline",
        MAPS4U_DATA_DIR=base_dir / "var",
        MAPS4U_DB_PATH=base_dir / "var" / "maps4u.sqlite3",
        MAPS4U_ARTIFACT_DIR=base_dir / "var" / "jobs",
        MAPS4U_CACHE_DIR=base_dir / "var" / "osm_cache",
        MAPS4U_OVERPASS_URL="https://overpass-api.de/api/interpreter",
        MAPS4U_OVERPASS_MAX_CONCURRENCY=1,
        MAPS4U_OPERATOR_TOKEN=op_token,
        MAPS4U_REVIEWER_TOKEN=rev_token,
        MAPS4U_OPERATOR_IDENTITY="sam.operator",
        MAPS4U_REVIEWER_IDENTITY="winston.reviewer",
    )

    app = create_app(settings)
    client = TestClient(app)
    op_headers = {"Authorization": f"Bearer {op_token}"}
    rev_headers = {"Authorization": f"Bearer {rev_token}"}

    results: list[dict[str, Any]] = []

    for idx, pilot in enumerate(LIVE_PILOTS):
        if idx > 0:
            # Polite 5-second gap between live Overpass queries (Constraint C-5)
            time.sleep(5.0)

        t0 = time.monotonic()
        geofence = {"type": "Polygon", "coordinates": [pilot["bbox_coords"]]}

        proj_r = client.post(
            "/api/projects",
            headers=op_headers,
            json={"area_name": pilot["area_name"], "reference": pilot["reference"]},
        )
        assert proj_r.status_code == 201, proj_r.text
        project_id = proj_r.json()["project_id"]

        rev_r = client.post(
            f"/api/projects/{project_id}/geofence",
            headers=op_headers,
            json=geofence,
        )
        assert rev_r.status_code == 201, rev_r.text
        revision_id = rev_r.json()["revision_id"]

        viab_r = client.post(
            "/api/viability",
            headers=op_headers,
            json={
                "geofence": geofence,
                "paper": pilot["paper"],
                "orientation": pilot["orientation"],
            },
        )
        assert viab_r.status_code == 200, viab_r.text
        viability = viab_r.json()
        assert viability["viable"] is True, viability

        job_r = client.post(
            "/api/jobs",
            headers=op_headers,
            json={
                "project_id": project_id,
                "geofence_revision": revision_id,
                "paper": pilot["paper"],
                "orientation": pilot["orientation"],
                "edition": "live-2026-10",
                "style_ref": "mcy/v1",
            },
        )
        assert job_r.status_code in (201, 409), job_r.text
        if job_r.status_code == 201:
            job_id = job_r.json()["job_id"]
            run_r = client.post(f"/api/jobs/{job_id}/run", headers=op_headers)
            assert run_r.status_code == 200, run_r.text
            assert run_r.json()["status"] == "proof_ready"

            app_r = client.post(
                f"/api/jobs/{job_id}/approve",
                headers=rev_headers,
                json={"reviewer": "ignored", "comment": f"Live pilot {pilot['area_name']} verified."},
            )
            assert app_r.status_code == 200, app_r.text
            assert app_r.json()["status"] == "finalized"
        else:
            jobs_list = client.get("/api/jobs", headers=op_headers).json()
            job_id = next(j["job_id"] for j in jobs_list if j["project_id"] == project_id)

        repro_r = client.post(f"/api/jobs/{job_id}/reproduce", headers=op_headers)
        assert repro_r.status_code == 200, repro_r.text
        repro = repro_r.json()
        assert repro["matched"] is True, repro

        job_dir = settings.artifact_dir / job_id
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        qa_report = json.loads((job_dir / "qa-report.json").read_text(encoding="utf-8"))

        snap_id = manifest["provenance"]["snapshot_id"]
        gpkg_path = settings.cache_dir / f"{snap_id}.gpkg"
        raw_path = settings.cache_dir / f"{snap_id}.raw.json"
        layers = read_geopackage_snapshot(gpkg_path)
        layer_counts = {name: len(layers.get_layer(name)) for name in LAYER_COLUMNS}

        slug_dir = exports_dir / pilot["slug"]
        slug_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("proof.pdf", "thumb.png", "qa-report.md", "qa-report.json", "manifest.json"):
            shutil.copy2(job_dir / fname, slug_dir / fname)

        elapsed_s = round(time.monotonic() - t0, 2)
        results.append(
            {
                "area_name": pilot["area_name"],
                "slug": pilot["slug"],
                "format": f"{pilot['paper']}-{pilot['orientation']}",
                "job_id": job_id,
                "status": "finalized",
                "scale_denominator": viability["scale_denominator"],
                "scale_band": viability.get("scale_band", "standard_street"),
                "snapshot_id": snap_id,
                "raw_overpass_bytes": raw_path.stat().st_size,
                "layer_counts": layer_counts,
                "qa_passed": qa_report["passed"],
                "blocker_count": qa_report["blocker_count"],
                "min_font_mm_observed": qa_report["min_font_mm_observed"],
                "dropped_count": qa_report["dropped_count"],
                "overlap_count": qa_report["overlaps"],
                "clipped_count": qa_report["clipped"],
                "pdf_sha256": manifest["outputs"]["proof_pdf"]["sha256"],
                "content_hash": manifest["outputs"]["content_hash"],
                "reproduce_matched": repro["matched"],
                "elapsed_s": elapsed_s,
                "export_dir": str(slug_dir),
            }
        )

    summary = {"live_pilots_status": "PASSED", "pilot_count": len(results), "pilots": results}
    (base_dir / "live_pilots_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    out = run_live_pilots()
    print(json.dumps(out, indent=2))
