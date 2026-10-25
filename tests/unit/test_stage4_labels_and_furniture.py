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


def test_nan_names_are_filtered_from_labels(test_settings: Settings) -> None:
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    fset = load_features_from_gpkg(extract.gpkg_path)
    fset.roads.loc[fset.roads.index[0], "name"] = float("nan")
    if not fset.parks.empty:
        fset.parks.loc[fset.parks.index[0], "name"] = float("nan")
    geofence = box(153.085, -26.660, 153.105, -26.645)
    tpl = get_template("A4", "landscape")
    style = load_style_yaml()
    plan = style_plan(fset, geofence, tpl, style, scale_denominator=10000.0)
    canvas = CairoCanvas()
    canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid = canvas.embedded_font(DEFAULT_TTF_PATH)
    res = place_labels(fset, geofence, plan, tpl, style, canvas, fid, seed=0)
    assert all(p.text.lower() != "nan" for p in res.placed)
    assert all(d.text.lower() != "nan" for d in res.dropped)


def test_v103_same_name_distance_deduplication_and_commercial_poi_filtering(
    test_settings: Settings,
) -> None:
    import pandas as pd
    from shapely.geometry import LineString, Point

    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)
    fset = load_features_from_gpkg(extract.gpkg_path)

    # Add a commercial motel to places and two short adjacent road segments with the same street name
    motel_row = pd.DataFrame(
        [
            {
                "osm_id": 888001,
                "name": "Top Spot Motel",
                "place_type": "motel",
                "importance": 50,
                "maps4u_class": "place",
                "corrected": 0,
                "correction_id": None,
                "geometry": Point(153.092, -26.652),
            }
        ]
    )
    fset.places = pd.concat([fset.places, motel_row], ignore_index=True)

    dup_roads = pd.DataFrame(
        [
            {
                "osm_id": 888010,
                "name": "Duporth Avenue",
                "ref": None,
                "highway": "secondary",
                "oneway": "no",
                "surface": "asphalt",
                "z_order_base": 14,
                "maps4u_class": "collector",
                "corrected": 0,
                "correction_id": None,
                "geometry": LineString([(153.088, -26.651), (153.091, -26.651)]),
            },
            {
                "osm_id": 888011,
                "name": "Duporth Avenue",
                "ref": None,
                "highway": "secondary",
                "oneway": "no",
                "surface": "asphalt",
                "z_order_base": 14,
                "maps4u_class": "collector",
                "corrected": 0,
                "correction_id": None,
                "geometry": LineString([(153.091, -26.651), (153.093, -26.651)]),
            },
        ]
    )
    fset.roads = pd.concat([fset.roads, dup_roads], ignore_index=True)

    geofence = box(153.085, -26.660, 153.105, -26.645)
    tpl = get_template("A4", "landscape")
    style = load_style_yaml()
    plan = style_plan(fset, geofence, tpl, style, scale_denominator=10000.0)
    canvas = CairoCanvas()
    canvas.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
    fid = canvas.embedded_font(DEFAULT_TTF_PATH)
    res = place_labels(fset, geofence, plan, tpl, style, canvas, fid, seed=0)

    # Commercial motel is filtered from placed labels
    assert all(p.text != "Top Spot Motel" for p in res.placed)
    # Adjacent duplicate road segments of 'Duporth Avenue' are de-duplicated via same_name_spacing
    duporth_placed = [p for p in res.placed if p.text == "Duporth Avenue"]
    assert len(duporth_placed) == 1
    assert any(d.text == "Duporth Avenue" and d.reason == "same_name_spacing" for d in res.dropped)

    composed = compose_furniture(
        canvas=canvas,
        plan=plan,
        labels=res,
        template=tpl,
        style=style,
        font_id=fid,
        area_name="Maroochydore",
        edition="2026-10",
    )
    assert len(composed.street_index) >= 1
    assert any(op.get("op") == "text" and "STREET INDEX" in str(op.get("glyphs")) for op in canvas.ops_log)
