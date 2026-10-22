"""Core domain models for Maps4U."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PaperSize = Literal["A3", "A4", "A5"]
Orientation = Literal["landscape", "portrait"]
JobStatus = Literal[
    "created",
    "validating",
    "queued",
    "assessing",
    "acquiring",
    "transforming",
    "styling",
    "labelling",
    "composing",
    "rendering",
    "verifying",
    "proof_ready",
    "finalized",
    "rejected",
    "failed",
]


@dataclass(frozen=True)
class BBox:
    """WGS84 bounding box (min_lon, min_lat, max_lon, max_lat)."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def normalized(self, precision: int = 6) -> BBox:
        return BBox(
            min_lon=round(self.min_lon, precision),
            min_lat=round(self.min_lat, precision),
            max_lon=round(self.max_lon, precision),
            max_lat=round(self.max_lat, precision),
        )

    def to_string(self, precision: int = 6) -> str:
        b = self.normalized(precision)
        return f"{b.min_lon:.{precision}f},{b.min_lat:.{precision}f},{b.max_lon:.{precision}f},{b.max_lat:.{precision}f}"

    def to_overpass_bbox(self, precision: int = 6) -> str:
        """Overpass QL bbox order is (south, west, north, east) = (min_lat, min_lon, max_lat, max_lon)."""
        b = self.normalized(precision)
        return f"{b.min_lat:.{precision}f},{b.min_lon:.{precision}f},{b.max_lat:.{precision}f},{b.max_lon:.{precision}f}"


@dataclass
class JobRecord:
    job_id: str
    area_name: str
    geofence_geojson: str
    paper: PaperSize
    orientation: Orientation
    style_ref: str
    status: JobStatus = "created"
    project_id: str | None = None
    geofence_revision: str | None = None
    spec_id: str | None = None
    edition: str | None = "ed1"
    corrections_ref: str | None = None
    scale_denominator: float | None = None
    min_font_mm: float | None = None
    thumbnail_path: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
