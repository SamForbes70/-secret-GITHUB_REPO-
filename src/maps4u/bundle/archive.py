"""Provenance manifest generator, frozen input archiver, and reproducibility verifier (DATA-001..003)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from maps4u.core.config import Settings, resolve_resource_path
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, E_STORAGE, Maps4UError
from maps4u.core.ids import canonical_json_bytes, sha256_hex
from maps4u.geo.cache import read_geopackage_snapshot
from maps4u.geo.corrections import apply_corrections, resolve_safe_corrections_path
from maps4u.labels.engine import place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas, render_png_thumbnail
from maps4u.render.style_engine import load_style_by_ref, load_style_yaml, style_plan


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
    gpkg_sha256: str | None = None,
    templates_sha256: str | None = None,
    style_source_path: Path | None = None,
    templates_source_path: Path | None = None,
    corrections_source_path: Path | None = None,
    render_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_dir = out_dir / "frozen_inputs"
    frozen_dir.mkdir(parents=True, exist_ok=True)

    if style_source_path is not None and style_source_path.is_file():
        shutil.copyfile(style_source_path, frozen_dir / "style.yaml")
    if templates_source_path is not None and templates_source_path.is_file():
        shutil.copyfile(templates_source_path, frozen_dir / "paper_templates.yaml")
        if templates_sha256 is None:
            templates_sha256 = sha256_hex(templates_source_path.read_bytes())
    if corrections_source_path is not None and corrections_source_path.is_file():
        shutil.copyfile(corrections_source_path, frozen_dir / "corrections.yaml")

    provenance: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot_sha256,
        "osm_base_date": osm_base_date,
        "licence": "ODbL-1.0 (OpenStreetMap contributors)",
        "style_ref": style_ref,
        "style_sha256": style_sha256,
        "corrections_sha256": corrections_sha256,
    }
    if gpkg_sha256 is not None:
        provenance["gpkg_sha256"] = gpkg_sha256
    if templates_sha256 is not None:
        provenance["templates_sha256"] = templates_sha256
    if render_config is not None:
        provenance["render_config"] = render_config

    manifest_data: dict[str, Any] = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "spec_id": spec_id,
        "provenance": provenance,
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
    """Re-render a finalized job from frozen inputs, verifying all input hashes first (DATA-001, DATA-002)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    job_dir = settings.artifact_dir / job_id
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.is_file():
        raise Maps4UError(E_NOT_FOUND, f"Manifest for job {job_id!r} not found", status_code=404)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prov = manifest.get("provenance") or {}
    snapshot_id = str(prov["snapshot_id"])
    expected_snapshot_sha = str(prov["snapshot_sha256"])
    style_ref = str(prov.get("style_ref") or settings.maps4u_default_style)
    expected_style_sha = str(prov.get("style_sha256") or "")
    expected_corr_sha = prov.get("corrections_sha256")
    expected_tpl_sha = prov.get("templates_sha256")
    frozen_cfg = prov.get("render_config") or {}

    with db_session(settings.db_path) as conn:
        j_row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        s_row = conn.execute(
            "SELECT * FROM osm_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
    if j_row is None or s_row is None:
        raise Maps4UError(E_NOT_FOUND, f"Job or snapshot record missing for {job_id!r}", status_code=404)

    raw_path = Path(str(s_row["raw_path"]))
    gpkg_path = Path(str(s_row["gpkg_path"]))
    if not raw_path.is_file():
        raise Maps4UError(
            E_STORAGE,
            f"Immutable raw OSM snapshot missing for snapshot_id {snapshot_id!r}: {raw_path}",
            details={"job_id": job_id, "snapshot_id": snapshot_id},
            status_code=409,
        )
    actual_raw_sha = sha256_hex(raw_path.read_bytes())
    if actual_raw_sha != expected_snapshot_sha or str(s_row["sha256"]) != expected_snapshot_sha:
        raise Maps4UError(
            E_STORAGE,
            f"OSM snapshot SHA-256 mismatch for job {job_id!r} (snapshot {snapshot_id!r})",
            details={
                "job_id": job_id,
                "snapshot_id": snapshot_id,
                "expected_sha256": expected_snapshot_sha,
                "actual_sha256": actual_raw_sha,
            },
            status_code=409,
        )

    geofence_geom = shape(json.loads(str(j_row["geofence_geojson"])))
    paper = str(j_row["paper"])
    orientation = str(j_row["orientation"])
    area_name = str(j_row["area_name"])
    edition = str(j_row["edition"] or "2026-10")
    scale_denominator = float(frozen_cfg.get("scale_denominator") or j_row["scale_denominator"] or 12500.0)
    insets_enabled = bool(frozen_cfg.get("insets_enabled", settings.maps4u_insets_enabled))
    render_dpi = int(frozen_cfg.get("render_dpi", settings.maps4u_render_dpi))
    corrections_ref = j_row["corrections_ref"]

    features = read_geopackage_snapshot(
        gpkg_path,
        raw_fallback_path=raw_path,
        expected_raw_sha256=expected_snapshot_sha,
    )
    frozen_dir = job_dir / "frozen_inputs"
    if corrections_ref or expected_corr_sha:
        frozen_corr = frozen_dir / "corrections.yaml"
        if frozen_corr.is_file():
            corr_path = frozen_corr
        else:
            if not corrections_ref:
                raise Maps4UError(
                    E_STORAGE,
                    f"Job {job_id!r} requires corrections_sha256={expected_corr_sha!r}, but corrections_ref is missing",
                    status_code=409,
                )
            with db_session(settings.db_path) as corr_conn:
                corr_path = resolve_safe_corrections_path(
                    str(corrections_ref),
                    data_dir=settings.maps4u_data_dir,
                    artifact_dir=settings.artifact_dir,
                    conn=corr_conn,
                )
        if not corr_path.is_file():
            raise Maps4UError(
                E_STORAGE,
                f"Corrections file for job {job_id!r} is missing: {corr_path}",
                details={"job_id": job_id, "corrections_ref": str(corrections_ref)},
                status_code=409,
            )
        actual_corr_sha = sha256_hex(corr_path.read_bytes())
        if expected_corr_sha and actual_corr_sha != str(expected_corr_sha):
            raise Maps4UError(
                E_STORAGE,
                f"Corrections file SHA-256 mismatch for job {job_id!r}: expected {expected_corr_sha}, got {actual_corr_sha}",
                details={
                    "job_id": job_id,
                    "expected_sha256": expected_corr_sha,
                    "actual_sha256": actual_corr_sha,
                },
                status_code=409,
            )
        features, _ = apply_corrections(features, corr_path)

    frozen_tpl = frozen_dir / "paper_templates.yaml"
    templates_path = (
        frozen_tpl
        if frozen_tpl.is_file()
        else resolve_resource_path("config/paper_templates.yaml", explicit_base=settings.maps4u_config_dir)
    )
    if expected_tpl_sha:
        if not templates_path.is_file():
            raise Maps4UError(
                E_STORAGE,
                f"Paper templates file missing for job {job_id!r}: {templates_path}",
                status_code=409,
            )
        actual_tpl_sha = sha256_hex(templates_path.read_bytes())
        if actual_tpl_sha != str(expected_tpl_sha):
            raise Maps4UError(
                E_STORAGE,
                f"Paper templates SHA-256 mismatch for job {job_id!r}: expected {expected_tpl_sha}, got {actual_tpl_sha}",
                details={
                    "job_id": job_id,
                    "expected_sha256": expected_tpl_sha,
                    "actual_sha256": actual_tpl_sha,
                },
                status_code=409,
            )

    style_schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    tpl = get_template(paper, orientation, path=templates_path)  # type: ignore[arg-type]
    frozen_style = frozen_dir / "style.yaml"
    try:
        if frozen_style.is_file():
            style = load_style_yaml(style_path=frozen_style, schema_path=style_schema_path)
        else:
            style = load_style_by_ref(style_ref, style_dir=settings.maps4u_style_dir, schema_path=style_schema_path)
    except Maps4UError as exc:
        raise Maps4UError(
            E_STORAGE,
            f"Style {style_ref!r} required to reproduce job {job_id!r} is missing or invalid: {exc.message}",
            details={"job_id": job_id, "style_ref": style_ref},
            status_code=409,
        ) from exc

    if expected_style_sha and style.sha256 != expected_style_sha:
        raise Maps4UError(
            E_STORAGE,
            f"Style {style_ref!r} SHA-256 mismatch for job {job_id!r}: expected {expected_style_sha}, got {style.sha256}",
            details={
                "job_id": job_id,
                "style_ref": style_ref,
                "expected_sha256": expected_style_sha,
                "actual_sha256": style.sha256,
            },
            status_code=409,
        )

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
        insets_enabled=insets_enabled,
    )

    repro_pdf = out_dir / "proof.pdf"
    repro_thumb = out_dir / "thumb.png"
    canvas.save_pdf(repro_pdf)
    render_png_thumbnail(canvas, repro_thumb, dpi=render_dpi)

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
