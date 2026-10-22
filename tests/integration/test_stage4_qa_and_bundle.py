"""Integration tests for Stage 4 S4.T3: QA preflight engine, failure injection, and governed manifest bundle."""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import box

from maps4u.bundle.archive import write_manifest
from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.core.state import verify_governed_outputs
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.labels.engine import LabelResult, PlacedLabel, place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template
from maps4u.qa.preflight import run_qa
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas
from maps4u.render.proof_renderer import render_proof
from maps4u.render.style_engine import load_style_yaml


def test_s4_t3_qa_preflight_and_governed_manifest_bundle(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    features = load_features_from_gpkg(extract.gpkg_path)

    geofence = box(153.085, -26.660, 153.105, -26.645)
    tpl = get_template("A4", "landscape")
    style = load_style_yaml()

    job_id = "job-stage4-qa-001"
    job_dir = test_settings.artifact_dir / job_id
    out = render_proof(
        features=features,
        geofence_wgs84=geofence,
        template=tpl,
        style=style,
        scale_denominator=12500.0,
        out_dir=job_dir,
        settings=test_settings,
        area_name="Maroochydore",
    )

    canvas = CairoCanvas()
    canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid = canvas.embedded_font(DEFAULT_TTF_PATH)
    labels = place_labels(features, geofence, out.plan, tpl, style, canvas, fid, seed=0)
    composed = compose_furniture(canvas, out.plan, labels, tpl, style, fid, area_name="Maroochydore")

    qa = run_qa(
        job_id=job_id,
        pdf_path=out.pdf_path,
        template=tpl,
        style=style,
        plan=out.plan,
        labels=labels,
        composed=composed,
        features=features,
        out_dir=job_dir,
    )
    assert qa.passed is True
    assert qa.blocker_count == 0
    assert qa.min_font_ok is True
    assert qa.overlaps == 0
    assert qa.clipped == 0
    assert qa.report_json_path is not None and qa.report_json_path.is_file()
    assert qa.report_md_path is not None and qa.report_md_path.is_file()

    manifest = write_manifest(
        job_id=job_id,
        out_dir=job_dir,
        spec_id="spec-001",
        snapshot_id=extract.snapshot_id,
        snapshot_sha256=extract.sha256,
        osm_base_date=extract.osm_base_date,
        style_ref=style.style_ref,
        style_sha256=style.sha256,
        corrections_sha256=None,
        pdf_path=out.pdf_path,
        thumb_path=out.thumb_path,
        qa_json_path=qa.report_json_path,
        qa_md_path=qa.report_md_path,
        content_hash=out.content_hash,
    )
    assert manifest["job_id"] == job_id
    assert verify_governed_outputs(test_settings.artifact_dir, job_id) == []

    # Injected failure test: overlapping & undersized (<1.5 mm) & clipped labels must trigger QA blockers
    bad_labels = LabelResult(
        placed=[
            PlacedLabel("Tiny St", "local", 4, 101, 20.0, 30.0, 15.0, 2.0, 0.0, fid, 1.2, "#000000", "above"),
            PlacedLabel("Overlap St", "local", 4, 102, 22.0, 30.5, 15.0, 2.0, 0.0, fid, 2.0, "#000000", "above"),
            PlacedLabel("Clipped St", "local", 4, 103, 1.0, 1.0, 25.0, 2.5, 0.0, fid, 2.0, "#000000", "above"),
        ],
        dropped=[],
    )
    qa_bad = run_qa(
        job_id="job-stage4-bad",
        pdf_path=out.pdf_path,
        template=tpl,
        style=style,
        plan=out.plan,
        labels=bad_labels,
        composed=composed,
        features=features,
        out_dir=tmp_path / "bad_qa",
    )
    assert qa_bad.passed is False
    assert qa_bad.blocker_count >= 3
    assert qa_bad.min_font_ok is False
    assert qa_bad.overlaps >= 1
    assert qa_bad.clipped >= 1
