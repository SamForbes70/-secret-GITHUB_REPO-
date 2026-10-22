"""Scale and legibility viability assessment engine (§6.3, S2.T2)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

from maps4u.core.errors import E_GEO_INVALID, Maps4UError
from maps4u.geo.crs import utm_epsg_for_lonlat
from maps4u.layout.templates import PaperTemplate

REMEDIATION_CHOICES: tuple[str, ...] = (
    "larger_sheet",
    "smaller_area",
    "accept_density_reduction",
    "inset_or_reverse_side_layout",
)

STANDARD_SCALE_DENOMINATORS: tuple[float, ...] = (
    1000.0,
    2000.0,
    2500.0,
    4000.0,
    5000.0,
    6000.0,
    7500.0,
    8000.0,
    10000.0,
    12500.0,
    15000.0,
    17500.0,
    20000.0,
    25000.0,
    30000.0,
    35000.0,
    40000.0,
    50000.0,
    75000.0,
    100000.0,
)


@dataclass(frozen=True)
class StyleSpec:
    """Cartographic style label & density configuration consumed by viability assessment."""

    style_ref: str = "mcy/v1"
    min_font_mm: float = 1.5
    mandatory_font_sizes_mm: dict[str, float] = field(
        default_factory=lambda: {
            "suburb": 4.5,
            "arterial": 2.6,
            "collector": 2.2,
            "local": 2.0,
        }
    )
    avg_label_box_mm2: float = 48.0
    packing_factor: float = 1.8
    density_warning_threshold: float = 0.85
    density_blocker_threshold: float = 1.25
    max_scale_denominator: float = 35000.0


@dataclass(frozen=True)
class Assessment:
    """Result of scale and legibility assessment (§6.3 contract)."""

    viable: bool
    scale_denominator: float
    natural_scale_denominator: float
    min_printed_mm: float
    configured_min_font_mm: float
    label_density_ratio: float
    working_crs_epsg: int
    extent_width_m: float
    extent_height_m: float
    area_km2: float
    map_area_w_mm: float
    map_area_h_mm: float
    warnings: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[dict[str, Any]] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "viable": self.viable,
            "scale_denominator": self.scale_denominator,
            "natural_scale_denominator": self.natural_scale_denominator,
            "min_printed_mm": self.min_printed_mm,
            "configured_min_font_mm": self.configured_min_font_mm,
            "label_density_ratio": self.label_density_ratio,
            "working_crs_epsg": self.working_crs_epsg,
            "extent_width_m": self.extent_width_m,
            "extent_height_m": self.extent_height_m,
            "area_km2": self.area_km2,
            "map_area_w_mm": self.map_area_w_mm,
            "map_area_h_mm": self.map_area_h_mm,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "choices": self.choices,
        }


def _round_to_standard_scale(natural_scale: float) -> float:
    for denom in STANDARD_SCALE_DENOMINATORS:
        if denom >= natural_scale:
            return denom
    return float(math.ceil(natural_scale / 5000.0) * 5000.0)


def assess(
    geofence: Polygon | MultiPolygon,
    template: PaperTemplate,
    style: StyleSpec | None = None,
    *,
    named_feature_count: int | None = None,
    min_font_override_mm: float | None = None,
) -> Assessment:
    """Compute print scale, font legibility, and label density viability per §6.3."""
    if geofence.is_empty or not geofence.is_valid:
        raise Maps4UError(E_GEO_INVALID, "Geofence must be a valid non-empty Polygon or MultiPolygon")

    style_cfg = style or StyleSpec()
    min_font_floor_mm = (
        float(min_font_override_mm)
        if min_font_override_mm is not None
        else float(style_cfg.min_font_mm)
    )

    centroid = geofence.centroid
    utm_epsg = utm_epsg_for_lonlat(float(centroid.x), float(centroid.y))
    gdf = gpd.GeoDataFrame({"geometry": [geofence]}, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    proj_geom = gdf.geometry.iloc[0]
    minx, miny, maxx, maxy = proj_geom.bounds

    width_m = max(1.0, float(maxx - minx))
    height_m = max(1.0, float(maxy - miny))
    area_km2 = float(proj_geom.area) / 1_000_000.0

    map_w_mm = float(template.map_area_mm.w)
    map_h_mm = float(template.map_area_mm.h)
    if map_w_mm <= 0 or map_h_mm <= 0:
        raise Maps4UError(E_GEO_INVALID, "Template map_area_mm must have positive width and height")

    natural_scale = max(width_m / (map_w_mm / 1000.0), height_m / (map_h_mm / 1000.0))
    scale_denominator = _round_to_standard_scale(natural_scale)

    # Style label sizes are fixed printed mm; also adjust if scale exceeds reference 1:25,000
    raw_min_font = min(style_cfg.mandatory_font_sizes_mm.values())
    scale_compression = min(1.0, style_cfg.max_scale_denominator / max(1.0, natural_scale))
    effective_min_printed_mm = round(raw_min_font * scale_compression, 3)

    # Density check: estimated named-feature labels vs capacity
    map_area_mm2 = template.map_area_mm.area_mm2
    label_capacity = max(
        1.0,
        map_area_mm2 / (style_cfg.avg_label_box_mm2 * style_cfg.packing_factor),
    )
    estimated_labels = (
        float(named_feature_count)
        if named_feature_count is not None
        else max(8.0, area_km2 * 18.0)
    )
    label_density_ratio = round(estimated_labels / label_capacity, 4)

    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    if effective_min_printed_mm < min_font_floor_mm:
        blockers.append(
            {
                "code": "FONT_BELOW_MINIMUM",
                "message": (
                    f"Minimum printed font size {effective_min_printed_mm:.2f} mm is below "
                    f"required threshold {min_font_floor_mm:.2f} mm."
                ),
                "min_printed_mm": effective_min_printed_mm,
                "threshold_mm": min_font_floor_mm,
            }
        )

    if natural_scale > style_cfg.max_scale_denominator:
        blockers.append(
            {
                "code": "SCALE_TOO_COARSE",
                "message": (
                    f"Natural scale 1:{natural_scale:.0f} exceeds maximum legible street map "
                    f"scale 1:{style_cfg.max_scale_denominator:.0f}."
                ),
                "natural_scale_denominator": round(natural_scale, 2),
                "max_scale_denominator": style_cfg.max_scale_denominator,
            }
        )

    if label_density_ratio >= style_cfg.density_blocker_threshold and named_feature_count is None:
        blockers.append(
            {
                "code": "EXTREME_LABEL_DENSITY",
                "message": (
                    f"Estimated label density ratio {label_density_ratio:.2f} exceeds blocker "
                    f"threshold {style_cfg.density_blocker_threshold:.2f}."
                ),
                "label_density_ratio": label_density_ratio,
            }
        )
    elif label_density_ratio >= style_cfg.density_warning_threshold:
        warnings.append(
            {
                "code": "HIGH_LABEL_DENSITY",
                "message": (
                    f"Estimated label density ratio {label_density_ratio:.2f} exceeds warning "
                    f"threshold {style_cfg.density_warning_threshold:.2f}; minor local streets may be dropped."
                ),
                "label_density_ratio": label_density_ratio,
            }
        )

    viable = len(blockers) == 0
    choices = list(REMEDIATION_CHOICES) if (blockers or warnings) else []

    return Assessment(
        viable=viable,
        scale_denominator=round(scale_denominator, 2),
        natural_scale_denominator=round(natural_scale, 2),
        min_printed_mm=effective_min_printed_mm,
        configured_min_font_mm=min_font_floor_mm,
        label_density_ratio=label_density_ratio,
        working_crs_epsg=utm_epsg,
        extent_width_m=round(width_m, 2),
        extent_height_m=round(height_m, 2),
        area_km2=round(area_km2, 4),
        map_area_w_mm=round(map_w_mm, 2),
        map_area_h_mm=round(map_h_mm, 2),
        warnings=warnings,
        blockers=blockers,
        choices=choices,
    )
