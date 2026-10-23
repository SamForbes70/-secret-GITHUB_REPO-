"""Provenance manifest generator and governed artifact bundle writer (Stage 4 S4.T3 & Stage 5 S5.T2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from maps4u.core.config import Settings, resolve_resource_path
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, Maps4UError
from maps4u.core.ids import canonical_json_bytes, sha256_hex
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.geo.corrections import apply_corrections, resolve_safe_corrections_path
from maps4u.labels.engine import place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas, render_png_thumbnail
from maps4u.render.style_engine import load_style_by_ref, style_plan


def write_manifest(
    job_id: str,
    out_dir: Path,
    *,
    spec_id: str,
    snapshot_id: str,
    snapshot_sha256: str,
    osm_base_date: str | None,
    style_ref: str,
    style_sha256: str,
    corrections_sha256: str | None,
    pdf_path: Path,
    thumb_path: Path,
    qa_json_path: Path,
    qa_md_path: Path,
    content_hash: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_data: dict[str, Any] = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "spec_id": spec_id,
        "provenance": {
            "snapshot_id": snapshot_id,
            "snapshot_sha256": snapshot_sha256,
            "osm_base_date": osm_base_date,
            "licence": "ODbL-1.0 (OpenStreetMap contributors)",
            "style_ref": style_ref,
            "style_sha256": style_sha256,
            "corrections_sha256": corrections_sha256,
        },
        "outputs": {
            "proof_pdf": {
                "filename": pdf_path.name,
                "sha256": sha256_hex(pdf_path.read_bytes()),
                "bytes": pdf_path.stat().st_size,
            },
            "thumb_png": {
                "filename": thumb_path.name,
                "sha256": sha256_hex(thumb_path.read_bytes()),
                "bytes": thumb_path.stat().st_size,
            },
            "qa_report_json": {
                "filename": qa_json_path.name,
                "sha256": sha256_hex(qa_json_path.read_bytes()),
                "bytes": qa_json_path.stat().st_size,
            },
            "qa_report_md": {
                "filename": qa_md_path.name,
                "sha256": sha256_hex(qa_md_path.read_bytes()),
                "bytes": qa_md_path.stat().st_size,
            },
            "content_hash": content_hash,
        },
    }
    manifest_data["manifest_sha256"] = sha256_hex(canonical_json_bytes(manifest_data))
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_data


def reproduce(
    job_id: str,
    settings: Settings,
    out_dir: Path,
) -> dict[str, Any]:
    """Reproduce a frozen job from its stored manifest + cached GeoPackage snapshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    job_dir = settings.artifact_dir / job_id
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.is_file():
        raise Maps4UError(E_NOT_FOUND, f"Manifest for job {job_id!r} not found", status_code=404)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_id = str(manifest["provenance"]["snapshot_id"])
    style_ref = str(manifest["provenance"].get("style_ref") or settings.maps4u_default_style)

    with db_session(settings.db_path) as conn:
        j_row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        s_row = conn.execute(
            "SELECT * FROM osm_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
    if j_row is None or s_row is None:
        raise Maps4UError(E_NOT_FOUND, f"Job or snapshot record missing for {job_id!r}", status_code=404)

    geofence_geom = shape(json.loads(str(j_row["geofence_geojson"])))
    paper = str(j_row["paper"])
    orientation = str(j_row["orientation"])
    area_name = str(j_row["area_name"])
    edition = str(j_row["edition"] or "2026-10")
    scale_denominator = float(j_row["scale_denominator"] or 12500.0)
    corrections_ref = j_row["corrections_ref"]

    features = load_features_from_gpkg(Path(str(s_row["gpkg_path"])))
    if corrections_ref:
        with db_session(settings.db_path) as corr_conn:
            corr_path = resolve_safe_corrections_path(
                str(corrections_ref),
                data_dir=settings.maps4u_data_dir,
                artifact_dir=settings.artifact_dir,
                conn=corr_conn,
            )
        features, _ = apply_corrections(features, corr_path)

    templates_path = resolve_resource_path("config/paper_templates.yaml", explicit_base=settings.maps4u_config_dir)
    style_schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    tpl = get_template(paper, orientation, path=templates_path)  # type: ignore[arg-type]
    style = load_style_by_ref(style_ref, style_dir=settings.maps4u_style_dir, schema_path=style_schema_path)
    plan = style_plan(features, geofence_geom, tpl, style, scale_denominator=scale_denominator)

    canvas = CairoCanvas()
    canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid = canvas.embedded_font(DEFAULT_TTF_PATH)
    labels = place_labels(features, geofence_geom, plan, tpl, style, canvas, fid, seed=0)

    for prim in plan.primitives:
        canvas.path(prim.ops, prim.stroke, prim.fill)
    compose_furniture(
        canvas=canvas,
        plan=plan,
        labels=labels,
        template=tpl,
        style=style,
        font_id=fid,
        area_name=area_name,
        edition=edition,
        insets_enabled=settings.maps4u_insets_enabled,
    )

    repro_pdf = out_dir / "proof.pdf"
    repro_thumb = out_dir / "thumb.png"
    canvas.save_pdf(repro_pdf)
    render_png_thumbnail(canvas, repro_thumb, dpi=settings.maps4u_render_dpi)

    orig_content_hash = str(manifest["outputs"]["content_hash"])
    repro_content_hash = canvas.content_hash()
    orig_pdf_sha = str(manifest["outputs"]["proof_pdf"]["sha256"])
    repro_pdf_sha = sha256_hex(repro_pdf.read_bytes())

    matched = (orig_content_hash == repro_content_hash) and (orig_pdf_sha == repro_pdf_sha)
    return {
        "job_id": job_id,
        "matched": matched,
        "original_content_hash": orig_content_hash,
        "reproduced_content_hash": repro_content_hash,
        "original_pdf_sha256": orig_pdf_sha,
        "reproduced_pdf_sha256": repro_pdf_sha,
        "reproduced_pdf_path": str(repro_pdf),
    }
