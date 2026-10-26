"""Deterministic label placement & STRtree collision avoidance engine (Stage 4 S4.T1)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import transform as shapely_transform
from shapely.strtree import STRtree

from maps4u.geo.crs import utm_epsg_for_lon_lat
from maps4u.geo.features import FeatureSet
from maps4u.layout.templates import PaperTemplate, RectMM
from maps4u.render.canvas import Canvas, GlyphPlacement
from maps4u.render.style_engine import DrawPlan, LoadedStyle, select_scale_band


@dataclass(frozen=True)
class PlacedLabel:
    text: str
    feature_class: str
    priority_rank: int
    osm_id: int
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    angle_deg: float
    font_id: str
    size_mm: float
    color: str
    candidate_pos: str
    repeat_index: int = 0
    halo_color: str | None = None
    halo_width_mm: float = 0.0

    def to_glyph(self) -> GlyphPlacement:
        return GlyphPlacement(
            text=self.text,
            x_mm=self.x_mm,
            y_mm=self.y_mm + self.h_mm * 0.78,
            angle_deg=self.angle_deg,
            font_id=self.font_id,
            size_mm=self.size_mm,
            color=self.color,
            halo_color=self.halo_color,
            halo_width_mm=self.halo_width_mm,
        )


@dataclass(frozen=True)
class DroppedLabel:
    text: str
    feature_class: str
    osm_id: int
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LabelResult:
    placed: list[PlacedLabel] = field(default_factory=list)
    dropped: list[DroppedLabel] = field(default_factory=list)
    seed: int = 0
    stats: dict[str, Any] = field(default_factory=dict)


def _classify_road_label_class(highway: str) -> str:
    if highway in ("motorway", "trunk", "primary"):
        return "arterial"
    if highway in ("secondary", "tertiary"):
        return "collector"
    if highway in ("service", "track", "path", "footway"):
        return "service"
    return "local"


def _candidate_offsets(order: list[str], w_mm: float, h_mm: float, pad_mm: float = 0.8) -> list[tuple[str, float, float]]:
    offsets: dict[str, tuple[float, float]] = {
        "above": (-w_mm / 2.0, -h_mm - pad_mm),
        "below": (-w_mm / 2.0, pad_mm),
        "right": (pad_mm, -h_mm / 2.0),
        "left": (-w_mm - pad_mm, -h_mm / 2.0),
        "top_right": (pad_mm, -h_mm - pad_mm),
        "top_left": (-w_mm - pad_mm, -h_mm - pad_mm),
        "bottom_right": (pad_mm, pad_mm),
        "bottom_left": (-w_mm - pad_mm, pad_mm),
    }
    result: list[tuple[str, float, float]] = []
    for name in order:
        if name in offsets:
            dx, dy = offsets[name]
            result.append((name, dx, dy))
    for name, (dx, dy) in offsets.items():
        if name not in order:
            result.append((name, dx, dy))
    return result


def _inside_map_rect(x_mm: float, y_mm: float, w_mm: float, h_mm: float, map_rect: RectMM, margin_mm: float = 0.4) -> bool:
    return (
        x_mm >= map_rect.x + margin_mm
        and y_mm >= map_rect.y + margin_mm
        and (x_mm + w_mm) <= (map_rect.right - margin_mm)
        and (y_mm + h_mm) <= (map_rect.bottom - margin_mm)
    )


def _collides_strtree(candidate_box: Polygon, placed_polys: list[Polygon], clearance_mm: float = 0.35) -> bool:
    if not placed_polys:
        return False
    c_minx, c_miny, c_maxx, c_maxy = candidate_box.bounds
    b_minx = c_minx - clearance_mm
    b_miny = c_miny - clearance_mm
    b_maxx = c_maxx + clearance_mm
    b_maxy = c_maxy + clearance_mm
    nearby = [
        p
        for p in placed_polys
        if not (p.bounds[2] < b_minx or p.bounds[0] > b_maxx or p.bounds[3] < b_miny or p.bounds[1] > b_maxy)
    ]
    if not nearby:
        return False
    buffered = candidate_box.buffer(clearance_mm)
    tree = STRtree(nearby)
    hits = tree.query(buffered, predicate="intersects")
    return len(hits) > 0


def place_labels(
    features: FeatureSet,
    geofence_wgs84: Polygon | MultiPolygon,
    plan: DrawPlan,
    template: PaperTemplate,
    style: LoadedStyle,
    canvas: Canvas,
    font_id: str,
    seed: int = 0,
) -> LabelResult:
    centroid = geofence_wgs84.centroid
    epsg = utm_epsg_for_lon_lat(float(centroid.x), float(centroid.y))
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    geofence_utm = shapely_transform(transformer.transform, geofence_wgs84)
    min_x, min_y, max_x, max_y = geofence_utm.bounds
    span_x = max(1e-3, max_x - min_x)
    span_y = max(1e-3, max_y - min_y)
    clip_poly = geofence_utm.buffer(max(span_x, span_y) * 0.02)
    map_rect = template.map_area_mm

    def _utm_to_mm(x_m: float, y_m: float) -> tuple[float, float]:
        px = map_rect.x + ((x_m - min_x) / span_x) * map_rect.w
        py = map_rect.y + ((max_y - y_m) / span_y) * map_rect.h
        return (round(px, 4), round(py, 4))

    fonts_cfg = style.raw.get("fonts", {})
    rules_cfg = style.raw.get("label_rules", {})
    priority_order: list[str] = list(
        rules_cfg.get(
            "priority_order",
            ["suburb", "landmark", "water", "park", "arterial", "collector", "local", "service"],
        )
    )
    candidate_order: list[str] = list(
        rules_cfg.get(
            "candidate_order",
            ["above", "below", "right", "left", "top_right", "top_left", "bottom_right", "bottom_left"],
        )
    )
    repeat_every_mm = float(rules_cfg.get("repeat_every_mm", 120.0))
    max_repeats = int(rules_cfg.get("max_repeats", 3))
    min_font_mm = float(rules_cfg.get("min_font_mm", 1.5))
    min_same_name_dist_mm = float(rules_cfg.get("min_same_name_distance_mm", 52.0))

    band = select_scale_band(style, scale_denominator=float(plan.scale_denominator))
    rank_map = {cls_name: idx for idx, cls_name in enumerate(priority_order)}

    # Collect raw label features with deterministic ordering
    candidates_raw: list[dict[str, Any]] = []

    def _clean_name(raw_val: Any) -> str:
        if raw_val is None:
            return ""
        if isinstance(raw_val, float) and math.isnan(raw_val):
            return ""
        s = str(raw_val).strip()
        if s.lower() in ("", "nan", "none", "<na>"):
            return ""
        return s

    true_place_types = {"suburb", "locality", "town", "hamlet", "island", "neighbourhood", "quarter", "place", ""}
    scenic_landmark_types = {"peak", "cape", "headland", "viewpoint", "attraction", "museum"}

    # 1. Places -> suburb (or scenic landmark; commercial lodging excluded)
    if not features.places.empty:
        for _, row in features.places.sort_values(by="osm_id").iterrows():
            name = _clean_name(row.get("name"))
            if not name:
                continue
            ptype = _clean_name(row.get("place_type")).lower()
            if ptype in true_place_types:
                target_cls = "suburb"
            elif ptype in scenic_landmark_types:
                target_cls = "landmark"
            else:
                continue
            g_utm = shapely_transform(transformer.transform, row.geometry)
            if not clip_poly.Intersects(g_utm) if hasattr(clip_poly, "Intersects") else not clip_poly.intersects(g_utm):
                continue
            pt = g_utm.centroid
            ax, ay = _utm_to_mm(float(pt.x), float(pt.y))
            candidates_raw.append(
                {
                    "text": name,
                    "feature_class": target_cls,
                    "osm_id": int(row["osm_id"]),
                    "anchors": [(ax, ay, 0.0, 0)],
                    "min_len_mm": 0.0,
                }
            )

    # 2. Landmarks -> landmark
    if not features.landmarks.empty:
        for _, row in features.landmarks.sort_values(by="osm_id").iterrows():
            name = _clean_name(row.get("name"))
            if not name:
                continue
            g_utm = shapely_transform(transformer.transform, row.geometry)
            if not clip_poly.intersects(g_utm):
                continue
            pt = g_utm.centroid
            ax, ay = _utm_to_mm(float(pt.x), float(pt.y))
            candidates_raw.append(
                {
                    "text": name,
                    "feature_class": "landmark",
                    "osm_id": int(row["osm_id"]),
                    "anchors": [(ax, ay, 0.0, 0)],
                    "min_len_mm": 0.0,
                }
            )

    # 3. Water & Parks polygons -> water, park
    for layer_key, label_cls in (("water", "water"), ("parks", "park")):
        gdf = features.get_layer(layer_key)
        if gdf.empty:
            continue
        for _, row in gdf.sort_values(by="osm_id").iterrows():
            name = _clean_name(row.get("name"))
            if not name:
                continue
            g_utm = shapely_transform(transformer.transform, row.geometry).intersection(clip_poly)
            if g_utm.is_empty:
                continue
            pt = g_utm.representative_point()
            ax, ay = _utm_to_mm(float(pt.x), float(pt.y))
            candidates_raw.append(
                {
                    "text": name,
                    "feature_class": label_cls,
                    "osm_id": int(row["osm_id"]),
                    "anchors": [(ax, ay, 0.0, 0)],
                    "min_len_mm": 0.0,
                }
            )

    # 4. Roads -> arterial, collector, local, service with repeats along long lines
    if not features.roads.empty:
        for _, row in features.roads.sort_values(by="osm_id").iterrows():
            name = _clean_name(row.get("name"))
            if not name:
                continue
            hwy = str(row.get("highway") or row.get("maps4u_class") or "residential")
            if hwy not in band.road_classes:
                continue
            label_cls = _classify_road_label_class(hwy)
            g_utm = shapely_transform(transformer.transform, row.geometry).intersection(clip_poly)
            if g_utm.is_empty:
                continue
            line: LineString | None = None
            if isinstance(g_utm, LineString):
                line = g_utm
            elif isinstance(g_utm, MultiLineString) and len(g_utm.geoms) > 0:
                line = max(g_utm.geoms, key=lambda g: g.length)
            if line is None or len(line.coords) < 2:
                continue

            mm_pts = [_utm_to_mm(float(c[0]), float(c[1])) for c in line.coords]
            mm_line = LineString(mm_pts)
            len_mm = float(mm_line.length)

            n_repeats = 1
            if len_mm >= repeat_every_mm * 1.5:
                n_repeats = min(max_repeats, max(1, int(len_mm // repeat_every_mm) + 1))

            anchors: list[tuple[float, float, float, int]] = []
            for r_idx in range(n_repeats):
                frac = (r_idx + 1) / (n_repeats + 1)
                pt_mm: Point = mm_line.interpolate(frac, normalized=True)
                anchors.append((float(pt_mm.x), float(pt_mm.y), 0.0, r_idx))

            candidates_raw.append(
                {
                    "text": name,
                    "feature_class": label_cls,
                    "osm_id": int(row["osm_id"]),
                    "anchors": anchors,
                    "line_len_mm": len_mm,
                }
            )

    # Stable sort: priority_rank ASC, name ASC, longest road segment first, osm_id ASC, seed tie-breaker
    candidates_raw.sort(
        key=lambda item: (
            rank_map.get(str(item["feature_class"]), 99),
            str(item["text"]),
            -round(float(item.get("line_len_mm", 0.0)), 2),
            (int(item["osm_id"]) ^ int(seed)) if seed else int(item["osm_id"]),
        )
    )

    placed: list[PlacedLabel] = []
    dropped: list[DroppedLabel] = []
    placed_polys: list[Polygon] = []
    placed_centers_by_name: dict[str, list[tuple[float, float]]] = {}

    for item in candidates_raw:
        f_cls = str(item["feature_class"])
        text = str(item["text"])
        name_key = text.strip().lower()
        osm_id = int(item["osm_id"])
        p_rank = rank_map.get(f_cls, 99)

        f_spec = fonts_cfg.get(f_cls) or fonts_cfg.get("local", {"size_mm": 2.0, "color": "#1f2937"})
        size_mm = float(f_spec.get("size_mm", 2.0))
        color = str(f_spec.get("color", "#1f2937"))
        halo_cfg = f_spec.get("halo") or {}
        halo_color = str(halo_cfg.get("color", "#ffffff")) if halo_cfg else None
        halo_width_mm = float(halo_cfg.get("width_mm", 0.0)) if halo_cfg else 0.0

        if size_mm < min_font_mm:
            dropped.append(
                DroppedLabel(
                    text=text,
                    feature_class=f_cls,
                    osm_id=osm_id,
                    reason="below_min_font",
                    details={"size_mm": size_mm, "min_font_mm": min_font_mm},
                )
            )
            continue

        w_mm, h_mm = canvas.measure_text_mm(text, font_id, size_mm)
        line_len_mm = float(item.get("line_len_mm", w_mm * 2.0))
        if f_cls in ("local", "service") and line_len_mm < w_mm * 0.45:
            dropped.append(
                DroppedLabel(
                    text=text,
                    feature_class=f_cls,
                    osm_id=osm_id,
                    reason="segment_too_short",
                    details={"line_len_mm": round(line_len_mm, 2), "label_w_mm": round(w_mm, 2)},
                )
            )
            continue

        cand_offsets = _candidate_offsets(candidate_order, w_mm, h_mm)
        if seed != 0 and len(cand_offsets) > 1:
            shift = abs(seed + osm_id) % len(cand_offsets)
            cand_offsets = cand_offsets[shift:] + cand_offsets[:shift]

        any_placed = False
        last_fail_reason = "collision"

        for ax, ay, angle_deg, r_idx in item["anchors"]:
            anchor_placed = False
            saw_in_bounds = False
            saw_spacing_block = False
            for pos_name, dx, dy in cand_offsets:
                lx = round(ax + dx, 4)
                ly = round(ay + dy, 4)
                if not _inside_map_rect(lx, ly, w_mm, h_mm, map_rect):
                    continue
                saw_in_bounds = True
                cx = lx + w_mm / 2.0
                cy = ly + h_mm / 2.0
                if min_same_name_dist_mm > 0.0 and any(
                    math.hypot(cx - px, cy - py) < min_same_name_dist_mm
                    for px, py in placed_centers_by_name.get(name_key, ())
                ):
                    saw_spacing_block = True
                    continue
                c_box = box(lx, ly, lx + w_mm, ly + h_mm)
                if not _collides_strtree(c_box, placed_polys):
                    placed_polys.append(c_box)
                    placed_centers_by_name.setdefault(name_key, []).append((cx, cy))
                    placed.append(
                        PlacedLabel(
                            text=text,
                            feature_class=f_cls,
                            priority_rank=p_rank,
                            osm_id=osm_id,
                            x_mm=lx,
                            y_mm=ly,
                            w_mm=round(w_mm, 4),
                            h_mm=round(h_mm, 4),
                            angle_deg=angle_deg,
                            font_id=font_id,
                            size_mm=size_mm,
                            color=color,
                            candidate_pos=pos_name,
                            repeat_index=r_idx,
                            halo_color=halo_color,
                            halo_width_mm=halo_width_mm,
                        )
                    )
                    anchor_placed = True
                    any_placed = True
                    break
            if not anchor_placed:
                if not saw_in_bounds:
                    last_fail_reason = "clipped"
                elif saw_spacing_block:
                    last_fail_reason = "same_name_spacing"

        if not any_placed:
            dropped.append(
                DroppedLabel(
                    text=text,
                    feature_class=f_cls,
                    osm_id=osm_id,
                    reason=last_fail_reason,
                    details={"w_mm": round(w_mm, 2), "h_mm": round(h_mm, 2)},
                )
            )

    return LabelResult(
        placed=placed,
        dropped=dropped,
        seed=seed,
        stats={
            "scale_band": band.name,
            "total_candidates": len(candidates_raw),
            "placed_count": len(placed),
            "dropped_count": len(dropped),
        },
    )
