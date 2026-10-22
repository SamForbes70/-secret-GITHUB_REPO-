"""Unit tests for Stage 3: S3.T1 (CairoCanvas & metrics/determinism) and S3.T2 (YAML Style Engine)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyPDF2 import PdfReader
from shapely.geometry import box

from maps4u.core.config import Settings
from maps4u.core.errors import Maps4UError
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.layout.templates import get_template
from maps4u.render.cairo_canvas import CairoCanvas
from maps4u.render.canvas import Fill, GlyphPlacement, PathOps, Stroke
from maps4u.render.style_engine import (
    load_style_yaml,
    select_scale_band,
    style_plan,
)


def test_s3_t1_cairo_canvas_deterministic_vector_pdf_and_thumbnail(tmp_path: Path) -> None:
    ttf_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    def _build_canvas(out_pdf: Path, out_thumb: Path) -> CairoCanvas:
        c = CairoCanvas()
        c.set_page((297.0, 210.0), bleed_mm=3.0)
        fid = c.embedded_font(ttf_path)
        c.path(
            PathOps([("M", (15.0, 15.0)), ("L", (120.0, 15.0)), ("L", (120.0, 80.0)), ("Z", ())]),
            Stroke("#4a4a4a", 0.8),
            Fill("#aad3df"),
        )
        c.text([GlyphPlacement("First Avenue", 30.0, 40.0, 0.0, fid, 2.6, "#111111")])
        c.save_pdf(out_pdf)
        c.render_thumbnail(out_thumb, dpi=96)
        return c

    pdf1 = tmp_path / "run1" / "proof.pdf"
    thumb1 = tmp_path / "run1" / "thumb.png"
    pdf2 = tmp_path / "run2" / "proof.pdf"
    thumb2 = tmp_path / "run2" / "thumb.png"

    c1 = _build_canvas(pdf1, thumb1)
    c2 = _build_canvas(pdf2, thumb2)

    assert c1.content_hash() == c2.content_hash()
    assert pdf1.read_bytes() == pdf2.read_bytes()
    assert thumb1.exists() and thumb1.stat().st_size > 100

    reader = PdfReader(str(pdf1))
    assert len(reader.pages) == 1
    w_mm, h_mm = c1.measure_text_mm("First Avenue", next(iter(c1.fonts)), 2.6)
    assert w_mm > 5.0
    assert h_mm == pytest.approx(2.6, rel=0.35)


def test_s3_t2_load_style_yaml_and_reject_invalid(tmp_path: Path) -> None:
    style = load_style_yaml()
    assert style.style_ref == "mcy/v1"
    assert style.style_version == "1.0.0"
    assert len(style.scale_bands) == 3

    bad_yaml = tmp_path / "bad_style.yaml"
    bad_yaml.write_text("style_version: '1.0.0'\nlayers: {}\n", encoding="utf-8")
    with pytest.raises(Maps4UError):
        load_style_yaml(bad_yaml)


def test_s3_t2_scale_band_selection_and_z_ordered_draw_plan(test_settings: Settings) -> None:
    style = load_style_yaml()
    band_detail = select_scale_band(style, 6000.0)
    band_std = select_scale_band(style, 12500.0)
    band_over = select_scale_band(style, 35000.0)
    assert band_detail.name == "detail"
    assert band_std.name == "standard_street"
    assert band_over.name == "overview"

    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    features = load_features_from_gpkg(extract.gpkg_path)

    geofence = box(153.085, -26.660, 153.105, -26.645)
    tpl = get_template("A4", "landscape")
    plan = style_plan(features, geofence, tpl, style, scale_denominator=12500.0)

    assert plan.style_ref == "mcy/v1"
    assert len(plan.primitives) > 0
    z_orders = [p.z_order for p in plan.primitives]
    assert z_orders == sorted(z_orders), "Primitives must be sorted monotonically by z_order"
    layers_present = {p.layer for p in plan.primitives}
    assert {"water", "parks", "roads"}.issubset(layers_present)
