"""End-to-end Phase 0 / Stage 1 live smoke test for maps4u-street-map-system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import geopandas as gpd
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.core.state import GOVERNED_OUTPUT_FILES
from maps4u.geo.acquire import get_or_fetch, load_features_from_extract
from maps4u.geo.corrections import apply_corrections
from maps4u.render.canvas import GlyphPlacement, PathOps, RecordingCanvas, Stroke


def run_smoke_test() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[1]
    fixture_overpass = repo_root / "tests" / "fixtures" / "overpass" / "mcy_sample.json"
    fixture_corr = repo_root / "tests" / "fixtures" / "corrections" / "valid_corrections.yaml"

    with tempfile.TemporaryDirectory(prefix="maps4u-smoke-") as tmp:
        tmp_path = Path(tmp)
        settings = Settings(
            MAPS4U_DATA_DIR=tmp_path / "var",
            MAPS4U_OVERPASS_URL=f"file://{fixture_overpass}",
            MAPS4U_QUEUE="inline",
            MAPS4U_ENV="test",
        )
        app = create_app(settings)
        client = TestClient(app)

        # 1. System endpoints
        r_health = client.get("/healthz")
        assert r_health.status_code == 200
        r_ready = client.get("/readyz")
        assert r_ready.status_code == 200
        r_meta = client.get("/api/meta")
        assert r_meta.status_code == 200

        # 2. Create project + geofence revision + job
        r_proj = client.post(
            "/api/projects",
            json={
                "area_name": "Maroochydore Smoke",
                "reference": "MCY-SMOKE",
                "notes": "Automated Phase 0 smoke test",
            },
        )
        assert r_proj.status_code == 201
        project_id = r_proj.json()["project_id"]

        geofence_poly = {
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
        r_geo = client.post(f"/api/projects/{project_id}/geofence", json=geofence_poly)
        assert r_geo.status_code == 201
        revision_id = r_geo.json()["revision_id"]

        r_job = client.post(
            "/api/jobs",
            json={
                "project_id": project_id,
                "geofence_revision": revision_id,
                "paper": "A4",
                "orientation": "landscape",
                "edition": "smoke1",
            },
        )
        assert r_job.status_code == 201
        job_id = r_job.json()["job_id"]
        spec_id = r_job.json()["spec_id"]

        # 3. Acquire & cache OSM data across all 8 layers
        bbox = BBox(
            min_lon=153.085,
            min_lat=-26.660,
            max_lon=153.105,
            max_lat=-26.645,
        )
        all_classes = [
            "roads",
            "water",
            "water_lines",
            "parks",
            "boundaries",
            "coastline",
            "places",
            "landmarks",
        ]
        extract1 = get_or_fetch(bbox=bbox, classes=all_classes, settings=settings)
        assert extract1.cache_hit is False
        extract2 = get_or_fetch(bbox=bbox, classes=all_classes, settings=settings)
        assert extract2.cache_hit is True
        assert extract1.snapshot_id == extract2.snapshot_id

        # 4. Apply client YAML corrections without mutating source GeoPackage
        fset = load_features_from_extract(extract1)
        corrected_fset, warnings = apply_corrections(fset, fixture_corr)
        assert warnings == []
        disk_roads = gpd.read_file(extract1.gpkg_path, layer="roads")
        assert "First Avenue" in set(disk_roads["name"].tolist())
        assert "The Esplanade" in set(corrected_fset.roads["name"].tolist())

        # 5. Verify RecordingCanvas deterministic drawlog and run full governed job pipeline to proof_ready
        canvas = RecordingCanvas()
        canvas.set_page((297.0, 210.0), bleed_mm=3.0)
        canvas.path(PathOps([("M", (10.0, 10.0)), ("L", (200.0, 100.0))]), Stroke("#222222", 1.0), None)
        canvas.text([GlyphPlacement("The Esplanade", 45.0, 60.0, 0.0, "font-noto", 2.2)])
        canvas.save_pdf(tmp_path / "recording_check" / "proof.pdf")

        r_run = client.post(f"/api/jobs/{job_id}/run")
        assert r_run.status_code == 200
        final_state = str(r_run.json()["status"])
        assert final_state == "proof_ready"

        job_dir = settings.artifact_dir / job_id
        for gov_file in GOVERNED_OUTPUT_FILES:
            assert (job_dir / gov_file).is_file()

        r_job_final = client.get(f"/api/jobs/{job_id}")
        assert r_job_final.status_code == 200
        assert r_job_final.json()["status"] == "proof_ready"

        return {
            "smoke_test": "PASSED",
            "project_id": project_id,
            "revision_id": revision_id,
            "job_id": job_id,
            "spec_id": spec_id,
            "snapshot_id": extract1.snapshot_id,
            "cache_hit_verified": extract2.cache_hit,
            "feature_counts": extract1.feature_counts,
            "final_job_status": final_state,
            "canvas_hash": canvas.content_hash(),
        }


if __name__ == "__main__":
    summary = run_smoke_test()
    print(json.dumps(summary, indent=2, sort_keys=True))
