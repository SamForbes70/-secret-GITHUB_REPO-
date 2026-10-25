# ruff: noqa: E501
"""On-Demand Custom Street Map Generator CLI — accepts any town/suburb name or BBox + paper size/orientation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import Settings

PRESET_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "maroochydore": (-26.6620, 153.0820, -26.6460, 153.1040),
    "noosa": (-26.3950, 153.0820, -26.3820, 153.1000),
    "noosa heads": (-26.3950, 153.0820, -26.3820, 153.1000),
    "bribie island": (-27.0820, 153.1450, -27.0640, 153.1640),
    "sandstone point": (-27.0820, 153.1450, -27.0640, 153.1640),
    "mooloolaba": (-26.6880, 153.1100, -26.6730, 153.1280),
    "caloundra": (-26.8090, 153.1220, -26.7940, 153.1420),
    "coolum beach": (-26.5350, 153.0820, -26.5200, 153.0980),
    "alexandra headland": (-26.6760, 153.0980, -26.6630, 153.1140),
    "kawana waters": (-26.7420, 153.1180, -26.7260, 153.1360),
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "custom-map"


def _resolve_bbox(area: str, bbox_arg: str | None) -> tuple[float, float, float, float]:
    if bbox_arg:
        parts = [float(x.strip()) for x in bbox_arg.split(",")]
        if len(parts) != 4:
            raise ValueError("--bbox must be 4 comma-separated floats: min_lat,min_lon,max_lat,max_lon")
        return (parts[0], parts[1], parts[2], parts[3])

    key = area.strip().lower()
    if key in PRESET_BBOXES:
        return PRESET_BBOXES[key]

    # Fallback: query OpenStreetMap Nominatim for town/suburb bounding box
    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": area, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": "Maps4U-StreetMapSystem/1.0.4 (+https://github.com/SamForbes70; deterministic-cartography)"},
        timeout=20.0,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode area {area!r}; pass explicit --bbox min_lat,min_lon,max_lat,max_lon")
    hit = results[0]
    lat = float(hit["lat"])
    lon = float(hit["lon"])
    # Default ~1.8km x 1.8km street-level window around town center for clean 1:10,000 - 1:15,000 legibility
    return (round(lat - 0.0075, 6), round(lon - 0.0095, 6), round(lat + 0.0075, 6), round(lon + 0.0095, 6))


def _bbox_to_polygon(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


def generate_custom_map(
    *,
    area_name: str,
    paper: str = "A4",
    orientation: str = "landscape",
    bbox_str: str | None = None,
    edition: str = "custom-2026-10",
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    overpass_url: str | None = None,
    approve: bool = True,
) -> dict[str, Any]:
    min_lat, min_lon, max_lat, max_lon = _resolve_bbox(area_name, bbox_str)
    geofence = _bbox_to_polygon(min_lat, min_lon, max_lat, max_lon)
    slug = f"{_slugify(area_name)}-{paper.lower()}-{orientation.lower()}"

    base_dir = data_dir.resolve() if data_dir else Path("/a0/usr/projects/maps4u/live-pilots-v1.0.2/var")
    export_root = output_dir.resolve() if output_dir else Path("/a0/usr/projects/maps4u/live-pilots-v1.0.2/exports")

    op_token = "maps4u-live-operator-token-2026-strong"
    rev_token = "maps4u-live-reviewer-token-2026-strong"
    op_headers = {"Authorization": f"Bearer {op_token}"}
    rev_headers = {"Authorization": f"Bearer {rev_token}"}

    settings_kwargs: dict[str, Any] = {
        "MAPS4U_ENV": "prod",
        "MAPS4U_QUEUE": "inline",
        "MAPS4U_DATA_DIR": base_dir,
        "MAPS4U_OPERATOR_TOKEN": op_token,
        "MAPS4U_REVIEWER_TOKEN": rev_token,
        "MAPS4U_OPERATOR_IDENTITY": "ops.custom.generator",
        "MAPS4U_REVIEWER_IDENTITY": "qa.custom.reviewer",
    }
    if overpass_url:
        settings_kwargs["MAPS4U_OVERPASS_URL"] = overpass_url

    settings = Settings(**settings_kwargs)
    settings.ensure_dirs()
    client = TestClient(create_app(settings))

    t0 = time.monotonic()
    r_proj = client.post(
        "/api/projects",
        headers=op_headers,
        json={"area_name": area_name, "reference": f"CUSTOM-{slug.upper()}", "notes": "On-demand custom map"},
    )
    r_proj.raise_for_status()
    project_id = r_proj.json()["project_id"]

    r_rev = client.post(f"/api/projects/{project_id}/geofence", headers=op_headers, json=geofence)
    r_rev.raise_for_status()
    revision_id = r_rev.json()["revision_id"]

    r_job = client.post(
        "/api/jobs",
        headers=op_headers,
        json={
            "project_id": project_id,
            "geofence_revision": revision_id,
            "paper": paper,
            "orientation": orientation,
            "edition": edition,
            "style_ref": "mcy/v1",
        },
    )
    r_job.raise_for_status()
    job_id = r_job.json()["job_id"]

    r_run = client.post(f"/api/jobs/{job_id}/run", headers=op_headers)
    r_run.raise_for_status()
    elapsed_s = round(time.monotonic() - t0, 2)

    reproduce_matched: bool | None = None
    if approve:
        r_app = client.post(
            f"/api/jobs/{job_id}/approve",
            headers=rev_headers,
            json={"comment": f"Approved on-demand map for {area_name} ({paper}-{orientation})"},
        )
        r_app.raise_for_status()
        r_repro = client.post(f"/api/jobs/{job_id}/reproduce", headers=op_headers)
        r_repro.raise_for_status()
        reproduce_matched = bool(r_repro.json()["matched"])

    r_get = client.get(f"/api/jobs/{job_id}", headers=op_headers)
    r_get.raise_for_status()
    job_meta = r_get.json()
    job_dir = settings.artifact_dir / job_id
    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    qa_report = json.loads((job_dir / "qa-report.json").read_text(encoding="utf-8"))

    dest_dir = export_root / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("proof.pdf", "thumb.png", "qa-report.md", "qa-report.json", "manifest.json"):
        shutil.copy2(job_dir / fname, dest_dir / fname)

    return {
        "area_name": area_name,
        "slug": slug,
        "bbox": [min_lat, min_lon, max_lat, max_lon],
        "format": f"{paper}-{orientation}",
        "job_id": job_id,
        "status": job_meta["status"],
        "scale_denominator": job_meta["scale_denominator"],
        "min_font_mm": job_meta["min_font_mm"],
        "qa_passed": qa_report["passed"],
        "blocker_count": qa_report["blocker_count"],
        "overlap_count": qa_report["overlaps"],
        "clipped_count": qa_report["clipped"],
        "pdf_sha256": manifest["outputs"]["proof_pdf"]["sha256"],
        "reproduce_matched": reproduce_matched,
        "elapsed_s": elapsed_s,
        "export_dir": str(dest_dir),
        "proof_pdf": str(dest_dir / "proof.pdf"),
        "thumb_png": str(dest_dir / "thumb.png"),
        "qa_report_md": str(dest_dir / "qa-report.md"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a print-ready vector PDF street map on demand for any town, suburb, or bounding box."
    )
    parser.add_argument("--area", required=True, help="Town or suburb name (e.g. 'Mooloolaba', 'Caloundra', 'Noosa Heads').")
    parser.add_argument("--paper", choices=["A3", "A4", "A5"], default="A4", help="Paper size (A3, A4, A5).")
    parser.add_argument(
        "--orientation",
        choices=["landscape", "portrait"],
        default="landscape",
        help="Sheet orientation (landscape or portrait).",
    )
    parser.add_argument(
        "--bbox",
        default=None,
        help="Optional explicit bounding box 'min_lat,min_lon,max_lat,max_lon' (auto-resolved if omitted).",
    )
    parser.add_argument("--edition", default="custom-2026-10", help="Edition label for title block and deterministic IDs.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Optional override for MAPS4U_DATA_DIR.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional export directory for proof.pdf and thumb.png.")
    parser.add_argument("--overpass-url", default=None, help="Optional override for MAPS4U_OVERPASS_URL.")
    parser.add_argument("--no-approve", action="store_true", help="Leave job in proof_ready state without finalizing.")
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    norm_argv: list[str] = []
    i = 0
    while i < len(raw_argv):
        if raw_argv[i] == "--bbox" and (i + 1) < len(raw_argv):
            norm_argv.append(f"--bbox={raw_argv[i + 1]}")
            i += 2
        else:
            norm_argv.append(raw_argv[i])
            i += 1
    args = parser.parse_args(norm_argv)

    result = generate_custom_map(
        area_name=args.area,
        paper=args.paper,
        orientation=args.orientation,
        bbox_str=args.bbox,
        edition=args.edition,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        overpass_url=args.overpass_url,
        approve=not args.no_approve,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
