"""Full end-to-end job pipeline executor (Stage 5 S5.T1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from maps4u.bundle.archive import write_manifest
from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, Maps4UError
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.geo.corrections import apply_corrections
from maps4u.labels.engine import place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template
from maps4u.qa.preflight import run_qa
from maps4u.render.assess import assess_viability
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas, render_png_thumbnail
from maps4u.render.style_engine import load_style_yaml, style_plan
from maps4u.worker.pipeline import PipelineRunner, StageCallable


def execute_job_pipeline(job_id: str, settings: Settings) -> dict[str, Any]:
    """Execute all governed stages for job_id from created/queued to proof_ready."""
    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
        job_data = dict(row)

    geofence_dict = json.loads(str(job_data["geofence_geojson"]))
    geofence_geom = shape(geofence_dict)
    minx, miny, maxx, maxy = geofence_geom.bounds
    bbox = BBox(min_lon=float(minx), min_lat=float(miny), max_lon=float(maxx), max_lat=float(maxy))

    paper = str(job_data["paper"])
    orientation = str(job_data["orientation"])
    area_name = str(job_data["area_name"])
    edition = str(job_data.get("edition") or "2026-10")
    style_ref = str(job_data.get("style_ref") or settings.maps4u_default_style)
    spec_id = str(job_data.get("spec_id") or "spec-default")
    corrections_ref = job_data.get("corrections_ref")

    tpl = get_template(paper, orientation)  # type: ignore[arg-type]
    style = load_style_yaml()
    job_dir = settings.artifact_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def _stage_validating(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"validated": True}

    def _stage_queued(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"queued": True}

    def _stage_assessing(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        res = assess_viability(geofence_geom, tpl)
        return {"scale_denominator": res.scale_denominator, "assessment": res}

    def _stage_acquiring(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
        extract = get_or_fetch(bbox=bbox, classes=classes, settings=settings)
        features = load_features_from_gpkg(extract.gpkg_path)
        corr_sha: str | None = None
        if corrections_ref:
            corr_path = Path(str(corrections_ref))
            if corr_path.is_file():
                features, _warnings = apply_corrections(features, corr_path)
                from maps4u.core.ids import sha256_hex

                corr_sha = sha256_hex(corr_path.read_bytes())
        return {"extract": extract, "features": features, "corrections_sha256": corr_sha}

    def _stage_transforming(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"transformed": True}

    def _stage_styling(_jid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        plan = style_plan(ctx["features"], geofence_geom, tpl, style, scale_denominator=float(ctx["scale_denominator"]))
        return {"plan": plan}

    def _stage_labelling(_jid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        canvas = CairoCanvas()
        canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
        fid = canvas.embedded_font(DEFAULT_TTF_PATH)
        labels = place_labels(ctx["features"], geofence_geom, ctx["plan"], tpl, style, canvas, fid, seed=0)
        return {"canvas": canvas, "font_id": fid, "labels": labels}

    def _stage_composing(_jid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        canvas: CairoCanvas = ctx["canvas"]
        for prim in ctx["plan"].primitives:
            canvas.path(prim.ops, prim.stroke, prim.fill)
        composed = compose_furniture(
            canvas=canvas,
            plan=ctx["plan"],
            labels=ctx["labels"],
            template=tpl,
            style=style,
            font_id=ctx["font_id"],
            area_name=area_name,
            edition=edition,
        )
        return {"composed": composed}

    def _stage_rendering(_jid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        canvas: CairoCanvas = ctx["canvas"]
        pdf_path = job_dir / "proof.pdf"
        thumb_path = job_dir / "thumb.png"
        canvas.save_pdf(pdf_path)
        render_png_thumbnail(canvas, thumb_path, dpi=settings.maps4u_render_dpi)
        return {"pdf_path": pdf_path, "thumb_path": thumb_path, "content_hash": canvas.content_hash()}

    def _stage_verifying(_jid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        qa = run_qa(
            job_id=job_id,
            pdf_path=ctx["pdf_path"],
            template=tpl,
            style=style,
            plan=ctx["plan"],
            labels=ctx["labels"],
            composed=ctx["composed"],
            features=ctx["features"],
            out_dir=job_dir,
        )
        extract = ctx["extract"]
        manifest = write_manifest(
            job_id=job_id,
            out_dir=job_dir,
            spec_id=spec_id,
            snapshot_id=extract.snapshot_id,
            snapshot_sha256=extract.sha256,
            osm_base_date=extract.osm_base_date,
            style_ref=style_ref,
            style_sha256=style.sha256,
            corrections_sha256=ctx.get("corrections_sha256"),
            pdf_path=ctx["pdf_path"],
            thumb_path=ctx["thumb_path"],
            qa_json_path=qa.report_json_path or (job_dir / "qa-report.json"),
            qa_md_path=qa.report_md_path or (job_dir / "qa-report.md"),
            content_hash=ctx["content_hash"],
        )
        return {"qa": qa, "manifest": manifest}

    def _stage_proof_ready(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"proof_ready": True}

    current_status = str(job_data["status"])
    stages_all: list[tuple[str, StageCallable]] = [
        ("validating", _stage_validating),
        ("queued", _stage_queued),
        ("assessing", _stage_assessing),
        ("acquiring", _stage_acquiring),
        ("transforming", _stage_transforming),
        ("styling", _stage_styling),
        ("labelling", _stage_labelling),
        ("composing", _stage_composing),
        ("rendering", _stage_rendering),
        ("verifying", _stage_verifying),
        ("proof_ready", _stage_proof_ready),
    ]
    if current_status == "queued":
        stages_all = stages_all[2:]
    elif current_status == "failed":
        stages_all = stages_all[1:]

    runner = PipelineRunner(settings)
    ctx = runner.run_stages(job_id, stages_all)

    now_iso = datetime.now(UTC).isoformat()
    qa = ctx["qa"]
    manifest = ctx["manifest"]
    with db_session(settings.db_path) as conn:
        conn.execute(
            """
            UPDATE jobs
            SET scale_denominator = ?, min_font_mm = ?, thumbnail_path = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                float(ctx["scale_denominator"]),
                float(qa.min_font_mm_observed),
                str(ctx["thumb_path"]),
                now_iso,
                job_id,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO qa_results (
                job_id, report_md_path, report_json_path, min_font_ok, overlaps, clipped, dropped_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                str(qa.report_md_path),
                str(qa.report_json_path),
                1 if qa.min_font_ok else 0,
                int(qa.overlaps),
                int(qa.clipped),
                json.dumps([d.text for d in ctx["labels"].dropped]),
            ),
        )
        for f in qa.findings:
            conn.execute(
                """
                INSERT INTO qa_findings (job_id, rule, severity, message, evidence_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, f.rule, f.severity, f.message, json.dumps(f.evidence, sort_keys=True)),
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO bundles (bundle_id, job_id, created_at, manifest_json, output_sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"bundle-{job_id}",
                job_id,
                now_iso,
                json.dumps(manifest, sort_keys=True),
                str(manifest["outputs"]["proof_pdf"]["sha256"]),
            ),
        )

    return {
        "job_id": job_id,
        "status": "proof_ready",
        "scale_denominator": float(ctx["scale_denominator"]),
        "min_font_mm": float(qa.min_font_mm_observed),
        "content_hash": str(ctx["content_hash"]),
        "proof_sha256": str(manifest["outputs"]["proof_pdf"]["sha256"]),
    }
