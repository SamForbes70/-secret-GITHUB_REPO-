"""Config-driven YAML Style Engine and z-ordered DrawPlan generator (Stage 3 S3.T2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from maps4u.core.config import resolve_resource_path
from maps4u.core.errors import E_STYLE_INVALID, Maps4UError
from maps4u.core.ids import canonical_json_bytes, sha256_hex
from maps4u.geo.crs import utm_epsg_for_lon_lat
from maps4u.geo.features import FeatureSet
from maps4u.layout.templates import PaperTemplate, RectMM
from maps4u.render.canvas import Fill, PathOps, Stroke

DEFAULT_STYLE_PATH = resolve_resource_path("styles/mcy/v1/style.yaml")
DEFAULT_STYLE_SCHEMA_PATH = resolve_resource_path("schemas/style.schema.json")


@dataclass(frozen=True)
class ScaleBand:
    name: str
    denominator_max: float
    simplify_tolerance_m: float
    road_classes: tuple[str, ...]
    include_layers: tuple[str, ...]


@dataclass(frozen=True)
class LoadedStyle:
    style_ref: str
    style_version: str
    approved: bool
    derived_from: str
    sha256: str
    raw: dict[str, Any]
    scale_bands: tuple[ScaleBand, ...]


@dataclass(frozen=True)
class DrawPrimitive:
    layer: str
    feature_class: str
    z_order: int
    osm_id: int
    name: str | None
    ops: PathOps
    stroke: Stroke | None = None
    fill: Fill | None = None


@dataclass(frozen=True)
class DrawPlan:
    style_ref: str
    style_version: str
    style_sha256: str
    scale_band: str
    scale_denominator: float
    working_crs_epsg: int
    primitives: list[DrawPrimitive] = field(default_factory=list)


def resolve_style_path(style_ref: str, style_dir: Path | None = None) -> Path:
    """Resolve a style_ref (e.g. 'mcy/v1') to its style.yaml path, rejecting unknown or unsafe refs."""
    cleaned = (style_ref or "").strip().strip("/")
    if not cleaned or ".." in Path(cleaned).parts or cleaned.startswith("."):
        raise Maps4UError(E_STYLE_INVALID, f"Invalid style reference: {style_ref!r}")
    rel = Path("styles") / cleaned / "style.yaml"
    candidates: list[Path] = []
    if style_dir is not None:
        candidates.append(style_dir / cleaned / "style.yaml")
        candidates.append(style_dir / rel)
    candidates.append(resolve_resource_path(rel, explicit_base=style_dir))
    for cand in candidates:
        if cand.is_file():
            return cand
    raise Maps4UError(
        E_STYLE_INVALID,
        f"Unknown style reference {style_ref!r}: style.yaml not found",
        details={"style_ref": style_ref},
    )


def load_style_by_ref(
    style_ref: str,
    style_dir: Path | None = None,
    schema_path: Path | None = None,
) -> LoadedStyle:
    """Load and validate a style by its canonical reference (e.g. 'mcy/v1')."""
    style_path = resolve_style_path(style_ref, style_dir=style_dir)
    loaded = load_style_yaml(style_path=style_path, schema_path=schema_path)
    if loaded.style_ref != style_ref:
        raise Maps4UError(
            E_STYLE_INVALID,
            f"Style metadata mismatch: requested {style_ref!r} but file declares {loaded.style_ref!r}",
        )
    return loaded


def list_available_styles(
    style_dir: Path | None = None,
    schema_path: Path | None = None,
) -> list[LoadedStyle]:
    """Discover and load all valid style.yaml definitions in style_dir."""
    base_dir = style_dir if (style_dir and style_dir.is_dir()) else resolve_resource_path("styles")
    styles: dict[str, LoadedStyle] = {}
    if base_dir.is_dir():
        for yml in sorted(base_dir.rglob("style.yaml")):
            try:
                st = load_style_yaml(style_path=yml, schema_path=schema_path)
                styles[st.style_ref] = st
            except Maps4UError:
                continue
    if not styles and DEFAULT_STYLE_PATH.is_file():
        st = load_style_yaml(style_path=DEFAULT_STYLE_PATH, schema_path=schema_path)
        styles[st.style_ref] = st
    return [styles[k] for k in sorted(styles.keys())]


def load_style_yaml(
    style_path: Path | None = None,
    schema_path: Path | None = None,
) -> LoadedStyle:
    target_style = style_path or DEFAULT_STYLE_PATH
    target_schema = schema_path or DEFAULT_STYLE_SCHEMA_PATH
    if not target_style.is_file():
        raise Maps4UError(E_STYLE_INVALID, f"Style file not found: {target_style}")
    if not target_schema.is_file():
        raise Maps4UError(E_STYLE_INVALID, f"Style schema not found: {target_schema}")

    try:
        raw_doc = yaml.safe_load(target_style.read_text(encoding="utf-8"))
    except Exception as exc:
        raise Maps4UError(E_STYLE_INVALID, f"Invalid YAML syntax in style file: {exc}") from exc

    if not isinstance(raw_doc, dict):
        raise Maps4UError(E_STYLE_INVALID, "Style YAML root must be a mapping")

    schema_doc = json.loads(target_schema.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=raw_doc, schema=schema_doc)
    except jsonschema.ValidationError as exc:
        raise Maps4UError(
            E_STYLE_INVALID,
            f"Style schema validation failed: {exc.message}",
            details={"path": list(exc.path)},
        ) from exc

    bands = tuple(
        ScaleBand(
            name=str(b["name"]),
            denominator_max=float(b["denominator_max"]),
            simplify_tolerance_m=float(b["simplify_tolerance_m"]),
            road_classes=tuple(str(c) for c in b["road_classes"]),
            include_layers=tuple(str(ly) for ly in b["include_layers"]),
        )
        for b in sorted(raw_doc["scale_bands"], key=lambda item: float(item["denominator_max"]))
    )
    meta = raw_doc["meta"]
    digest = sha256_hex(canonical_json_bytes(raw_doc))
    return LoadedStyle(
        style_ref=str(meta["style_ref"]),
        style_version=str(raw_doc["style_version"]),
        approved=bool(meta["approved"]),
        derived_from=str(meta["derived_from"]),
        sha256=digest,
        raw=raw_doc,
        scale_bands=bands,
    )


def select_scale_band(style: LoadedStyle, scale_denominator: float) -> ScaleBand:
    for band in style.scale_bands:
        if scale_denominator <= band.denominator_max:
            return band
    return style.scale_bands[-1]


def _geom_to_path_ops(
    geom: BaseGeometry,
    utm_bounds: tuple[float, float, float, float],
    map_rect: RectMM,
) -> PathOps:
    min_x, min_y, max_x, max_y = utm_bounds
    span_x = max(1e-3, max_x - min_x)
    span_y = max(1e-3, max_y - min_y)

    def _map_pt(x_m: float, y_m: float) -> tuple[float, float]:
        px = map_rect.x + ((x_m - min_x) / span_x) * map_rect.w
        py = map_rect.y + ((max_y - y_m) / span_y) * map_rect.h
        return (round(px, 4), round(py, 4))

    cmds: list[tuple[str, tuple[float, ...]]] = []

    def _add_coords(coords_seq: Any, close: bool) -> None:
        pts = list(coords_seq)
        if len(pts) < 2:
            return
        first = _map_pt(float(pts[0][0]), float(pts[0][1]))
        cmds.append(("M", first))
        for pt in pts[1:]:
            cmds.append(("L", _map_pt(float(pt[0]), float(pt[1]))))
        if close:
            cmds.append(("Z", ()))

    if isinstance(geom, LineString):
        _add_coords(geom.coords, close=False)
    elif isinstance(geom, MultiLineString):
        for part in geom.geoms:
            _add_coords(part.coords, close=False)
    elif isinstance(geom, Polygon):
        _add_coords(geom.exterior.coords, close=True)
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            _add_coords(poly.exterior.coords, close=True)

    return PathOps(commands=cmds)


def style_plan(
    features: FeatureSet,
    geofence_wgs84: Polygon | MultiPolygon,
    template: PaperTemplate,
    style: LoadedStyle,
    scale_denominator: float,
) -> DrawPlan:
    centroid = geofence_wgs84.centroid
    epsg = utm_epsg_for_lon_lat(float(centroid.x), float(centroid.y))
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    def _proj(geom: BaseGeometry) -> BaseGeometry:
        return shapely_transform(transformer.transform, geom)

    geofence_utm = _proj(geofence_wgs84)
    min_x, min_y, max_x, max_y = geofence_utm.bounds
    buf_m = max(max_x - min_x, max_y - min_y) * 0.02
    clip_poly = geofence_utm.buffer(buf_m)
    utm_bounds = (min_x, min_y, max_x, max_y)

    band = select_scale_band(style, scale_denominator)
    layers_cfg = style.raw.get("layers", {})
    map_rect = template.map_area_mm
    primitives: list[DrawPrimitive] = []

    bg_cfg = layers_cfg.get("background", {"fill": "#f9f6ef", "z": 0})
    bg_ops = PathOps(
        commands=[
            ("M", (map_rect.x, map_rect.y)),
            ("L", (map_rect.right, map_rect.y)),
            ("L", (map_rect.right, map_rect.bottom)),
            ("L", (map_rect.x, map_rect.bottom)),
            ("Z", ()),
        ]
    )
    primitives.append(
        DrawPrimitive(
            layer="background",
            feature_class="background",
            z_order=int(bg_cfg.get("z", 0)),
            osm_id=0,
            name=None,
            ops=bg_ops,
            stroke=Stroke("#cbd5e1", 0.25),
            fill=Fill(str(bg_cfg.get("fill", "#f9f6ef"))),
        )
    )

    def _emit_polygon_layer(layer_name: str) -> None:
        if layer_name not in band.include_layers:
            return
        cfg = layers_cfg.get(layer_name, {})
        gdf = features.get_layer(layer_name)
        if gdf.empty:
            return
        fill_color = cfg.get("fill")
        stroke_cfg = cfg.get("stroke")
        stroke_obj = (
            Stroke(
                str(stroke_cfg["color"]),
                float(stroke_cfg["width_mm"]),
                stroke_cfg.get("dash"),
            )
            if isinstance(stroke_cfg, dict)
            else None
        )
        fill_obj = Fill(str(fill_color)) if fill_color else None
        z_val = int(cfg.get("z", 1))

        for _, row in gdf.sort_values(by="osm_id").iterrows():
            geom_utm = _proj(row.geometry).intersection(clip_poly)
            if geom_utm.is_empty:
                continue
            if band.simplify_tolerance_m > 0:
                geom_utm = geom_utm.simplify(band.simplify_tolerance_m, preserve_topology=True)
            ops = _geom_to_path_ops(geom_utm, utm_bounds, map_rect)
            if ops.commands:
                primitives.append(
                    DrawPrimitive(
                        layer=layer_name,
                        feature_class=str(row.get("maps4u_class", layer_name)),
                        z_order=z_val,
                        osm_id=int(row["osm_id"]),
                        name=str(row["name"]) if row.get("name") else None,
                        ops=ops,
                        stroke=stroke_obj,
                        fill=fill_obj,
                    )
                )

    def _emit_line_layer(layer_name: str) -> None:
        if layer_name not in band.include_layers:
            return
        cfg = layers_cfg.get(layer_name, {})
        gdf = features.get_layer(layer_name)
        if gdf.empty:
            return
        stroke_cfg = cfg.get("stroke", {"color": "#666666", "width_mm": 0.3})
        stroke_obj = Stroke(
            str(stroke_cfg["color"]),
            float(stroke_cfg["width_mm"]),
            list(stroke_cfg["dash"]) if stroke_cfg.get("dash") else None,
        )
        z_val = int(cfg.get("z", 3))
        for _, row in gdf.sort_values(by="osm_id").iterrows():
            geom_utm = _proj(row.geometry).intersection(clip_poly)
            if geom_utm.is_empty:
                continue
            if band.simplify_tolerance_m > 0:
                geom_utm = geom_utm.simplify(band.simplify_tolerance_m, preserve_topology=True)
            ops = _geom_to_path_ops(geom_utm, utm_bounds, map_rect)
            if ops.commands:
                primitives.append(
                    DrawPrimitive(
                        layer=layer_name,
                        feature_class=str(row.get("maps4u_class", layer_name)),
                        z_order=z_val,
                        osm_id=int(row["osm_id"]),
                        name=str(row["name"]) if row.get("name") else None,
                        ops=ops,
                        stroke=stroke_obj,
                        fill=None,
                    )
                )

    _emit_polygon_layer("water")
    _emit_polygon_layer("parks")
    _emit_line_layer("water_lines")
    _emit_line_layer("coastline")

    if "roads" in band.include_layers and not features.roads.empty:
        roads_cfg = layers_cfg.get("roads", {})
        for _, row in features.roads.sort_values(by="osm_id").iterrows():
            hwy = str(row.get("highway") or row.get("maps4u_class") or "residential")
            if hwy not in band.road_classes and hwy not in roads_cfg:
                hwy = "residential"
            if hwy not in band.road_classes:
                continue
            rcfg = roads_cfg.get(hwy) or roads_cfg.get("residential", {})
            geom_utm = _proj(row.geometry).intersection(clip_poly)
            if geom_utm.is_empty:
                continue
            if band.simplify_tolerance_m > 0:
                geom_utm = geom_utm.simplify(band.simplify_tolerance_m, preserve_topology=True)
            ops = _geom_to_path_ops(geom_utm, utm_bounds, map_rect)
            if not ops.commands:
                continue
            base_z = int(rcfg.get("z", 12))
            casing_cfg = rcfg.get("casing", {"color": "#666666", "width_mm": 0.8})
            fill_cfg = rcfg.get("fill", {"color": "#ffffff", "width_mm": 0.5})
            osm_id = int(row["osm_id"])
            rname = str(row["name"]) if row.get("name") else None
            primitives.append(
                DrawPrimitive(
                    layer="roads",
                    feature_class=f"{hwy}_casing",
                    z_order=base_z,
                    osm_id=osm_id,
                    name=rname,
                    ops=ops,
                    stroke=Stroke(str(casing_cfg["color"]), float(casing_cfg["width_mm"])),
                    fill=None,
                )
            )
            primitives.append(
                DrawPrimitive(
                    layer="roads",
                    feature_class=f"{hwy}_fill",
                    z_order=base_z + 1,
                    osm_id=osm_id,
                    name=rname,
                    ops=ops,
                    stroke=Stroke(str(fill_cfg["color"]), float(fill_cfg["width_mm"])),
                    fill=None,
                )
            )

    _emit_line_layer("boundaries")

    primitives.sort(key=lambda p: (p.z_order, p.layer, p.osm_id, p.feature_class))
    return DrawPlan(
        style_ref=style.style_ref,
        style_version=style.style_version,
        style_sha256=style.sha256,
        scale_band=band.name,
        scale_denominator=round(scale_denominator, 2),
        working_crs_epsg=epsg,
        primitives=primitives,
    )
