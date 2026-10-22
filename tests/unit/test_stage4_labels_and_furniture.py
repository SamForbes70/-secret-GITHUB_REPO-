"""Unit tests for Stage 4: S4.T1 (Label placement & collision engine) and S4.T2/S4.T4 (Map furniture & inset composer)."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.labels.engine import place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template, load_all_templates
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas
from maps4u.render.style_engine import load_style_yaml, style_plan


def test_s4_t1_label_placement_determinism_collision_and_repeats(test_settings: Settings) -> None:
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    features = load_features_from_gpkg(extract.gpkg_path)

    geofence = box(153.085, -26.660, 153.105, -26.645)
    tpl = get_template("A4", "landscape")
    style = load_style_yaml()
    plan = style_plan(features, geofence, tpl, style, scale_denominator=10000.0)

    c1 = CairoCanvas()
    c1.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid1 = c1.embedded_font(DEFAULT_TTF_PATH)
    res1 = place_labels(features, geofence, plan, tpl, style, c1, fid1, seed=0)

    c2 = CairoCanvas()
    c2.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid2 = c2.embedded_font(DEFAULT_TTF_PATH)
    res2 = place_labels(features, geofence, plan, tpl, style, c2, fid2, seed=0)

    assert [p.text for p in res1.placed] == [p.text for p in res2.placed]
    assert [(p.x_mm, p.y_mm) for p in res1.placed] == [(p.x_mm, p.y_mm) for p in res2.placed]
    assert len(res1.placed) >= 5

    # Verify zero bounding-box collisions among placed labels and all within map_area_mm
    map_rect = tpl.map_area_mm
    boxes = []
    for p in res1.placed:
        assert p.size_mm >= 1.5
        b = box(p.x_mm, p.y_mm, p.x_mm + p.w_mm, p.y_mm + p.h_mm)
        assert p.x_mm >= map_rect.x - 0.01
        assert p.y_mm >= map_rect.y - 0.01
        assert p.x_mm + p.w_mm <= map_rect.right + 0.01
        assert p.y_mm + p.h_mm <= map_rect.bottom + 0.01
        for prev in boxes:
            assert not b.intersects(prev), f"Placed label {p.text} collides with an existing label"
        boxes.append(b)


@pytest.mark.parametrize("tpl_key", ["A3-landscape", "A3-portrait", "A4-landscape", "A4-portrait", "A5-landscape", "A5-portrait"])  # noqa: E501
def test_s4_t2_and_t4_compose_furniture_all_templates_and_insets(
    test_settings: Settings,
    tpl_key: str,
) -> None:
    paper, orientation = tpl_key.split("-")
    tpl = load_all_templates()[tpl_key]
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    features = load_features_from_gpkg(extract.gpkg_path)
    geofence = box(153.085, -26.660, 153.105, -26.645)
    style = load_style_yaml()
    plan = style_plan(features, geofence, tpl, style, scale_denominator=12500.0)

    canvas = CairoCanvas()
    canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid = canvas.embedded_font(DEFAULT_TTF_PATH)
    labels = place_labels(features, geofence, plan, tpl, style, canvas, fid, seed=0)

    composed_single = compose_furniture(
        canvas=canvas,
        plan=plan,
        labels=labels,
        template=tpl,
        style=style,
        font_id=fid,
        area_name="Maroochydore",
        edition="2026-10",
        insets_enabled=False,
    )
    assert composed_single.page_count == 1
    assert composed_single.has_attribution is True
    assert len(composed_single.legend_classes) >= 2
    assert len(composed_single.grid_cells) >= 4
    assert len(composed_single.street_index) >= 1

    composed_inset = compose_furniture(
        canvas=canvas,
        plan=plan,
        labels=labels,
        template=tpl,
        style=style,
        font_id=fid,
        area_name="Maroochydore",
        edition="2026-10",
        insets_enabled=True,
    )
    assert composed_inset.inset_enabled is True
    assert composed_inset.page_count == 2
