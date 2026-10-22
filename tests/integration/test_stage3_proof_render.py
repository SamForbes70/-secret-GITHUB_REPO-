"""Integration tests for Stage 3 S3.T3: First end-to-end vector proof PDF + thumbnail + structural checks."""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import box

from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.layout.templates import get_template
from maps4u.render.proof_renderer import render_proof, verify_pdf_structure
from maps4u.render.style_engine import load_style_yaml


def test_s3_t3_end_to_end_vector_proof_render_and_structural_checks(
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

    out1 = render_proof(
        features=features,
        geofence_wgs84=geofence,
        template=tpl,
        style=style,
        scale_denominator=12500.0,
        out_dir=tmp_path / "job1",
        settings=test_settings,
        area_name="Maroochydore",
    )
    out2 = render_proof(
        features=features,
        geofence_wgs84=geofence,
        template=tpl,
        style=style,
        scale_denominator=12500.0,
        out_dir=tmp_path / "job2",
        settings=test_settings,
        area_name="Maroochydore",
    )

    assert out1.pdf_path.exists()
    assert out1.thumb_path.exists()
    assert out1.drawlog_path.exists()
    assert out1.content_hash == out2.content_hash
    assert out1.pdf_sha256 == out2.pdf_sha256

    checks = verify_pdf_structure(out1.pdf_path, expected_size_mm=tpl.page_mm)
    assert checks["page_count"] == 1
    assert checks["page_size_matches"] is True
    assert checks["has_vector_paths"] is True
    assert checks["fonts_embedded"] is True
    assert checks["has_odbl_attribution"] is True
    assert checks["has_unexpected_raster"] is False
