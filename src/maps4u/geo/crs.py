"""CRS selection (UTM zone calculation), bbox helpers, and geofence validation."""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.validation import explain_validity

from maps4u.core.errors import E_GEO_INVALID, E_GEO_TOO_LARGE, E_GEO_UNSUPPORTED, Maps4UError
from maps4u.core.ids import canonical_json_bytes, sha256_hex
from maps4u.core.models import BBox

MAX_VERTICES_PER_RING = 200
MAX_AREA_KM2 = 600.0
MAX_MULTIPOLYGON_PARTS = 3


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    """Return EPSG code for the UTM zone containing (lon, lat) (ADR-6)."""
    zone = int((math.floor((lon + 180.0) / 6.0) % 60) + 1)
    return (32600 if lat >= 0 else 32700) + zone


utm_epsg_for_lon_lat = utm_epsg_for_lonlat


def bbox_from_geometry(geom: Polygon | MultiPolygon) -> BBox:
    minx, miny, maxx, maxy = geom.bounds
    return BBox(min_lon=float(minx), min_lat=float(miny), max_lon=float(maxx), max_lat=float(maxy))


def _round_coords(coords: Any, precision: int = 7) -> Any:
    if isinstance(coords, (list, tuple)):
        if len(coords) >= 2 and isinstance(coords[0], (int, float)):
            return [round(float(coords[0]), precision), round(float(coords[1]), precision)]
        return [_round_coords(c, precision) for c in coords]
    return coords


def compute_geometry_sha256(canonical_json: str | bytes) -> str:
    """Return the project-independent SHA-256 fingerprint of canonical GeoJSON bytes."""
    raw = canonical_json.encode("utf-8") if isinstance(canonical_json, str) else canonical_json
    return sha256_hex(raw)


def validate_and_canonicalise_geofence(
    geojson_geom: dict[str, Any],
    *,
    max_vertices: int = MAX_VERTICES_PER_RING,
    max_area_km2: float = MAX_AREA_KM2,
    max_parts: int = MAX_MULTIPOLYGON_PARTS,
    project_id: str | None = None,
) -> tuple[Polygon | MultiPolygon, str, str]:
    """Validate GeoJSON Polygon/MultiPolygon per §6.2 and return (geom, canonical_json, revision_id).

    When ``project_id`` is provided, ``revision_id`` is scoped to ``(project_id, geometry_sha256)``
    so two projects with identical geometry never collide on primary key (BUG-007).
    """
    gtype = geojson_geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        raise Maps4UError(E_GEO_INVALID, f"Unsupported geometry type: {gtype!r}")

    try:
        geom = shape(geojson_geom)
    except Exception as exc:
        raise Maps4UError(E_GEO_INVALID, f"Invalid GeoJSON geometry: {exc}") from exc

    if geom.is_empty:
        raise Maps4UError(E_GEO_INVALID, "Geofence geometry cannot be empty")

    if not geom.is_valid:
        reason = explain_validity(geom)
        raise Maps4UError(
            E_GEO_INVALID,
            f"Geofence polygon is self-intersecting or invalid: {reason}",
            details={"validity_reason": reason, "repair_hint": "Ensure boundary rings do not cross."},
        )

    polys: list[Polygon] = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    if len(polys) > max_parts:
        raise Maps4UError(
            E_GEO_INVALID,
            f"MultiPolygon exceeds maximum of {max_parts} parts ({len(polys)} supplied)",
        )

    for poly in polys:
        rings = [poly.exterior, *list(poly.interiors)]
        for ring in rings:
            if len(ring.coords) > max_vertices:
                raise Maps4UError(
                    E_GEO_INVALID,
                    f"Polygon ring has {len(ring.coords)} vertices; maximum allowed is {max_vertices}",
                )
            lons = [float(c[0]) for c in ring.coords]
            if max(lons) - min(lons) > 180.0:
                raise Maps4UError(E_GEO_UNSUPPORTED, "Antimeridian-crossing polygons are not supported")

    centroid = geom.centroid
    utm_epsg = utm_epsg_for_lonlat(float(centroid.x), float(centroid.y))
    gdf = gpd.GeoDataFrame({"geometry": [geom]}, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    area_km2 = float(gdf.geometry.area.iloc[0]) / 1_000_000.0
    if area_km2 <= 0.0:
        raise Maps4UError(E_GEO_INVALID, "Geofence area must be positive")
    if area_km2 > max_area_km2:
        raise Maps4UError(
            E_GEO_TOO_LARGE,
            f"Geofence area {area_km2:.2f} km² exceeds maximum allowed {max_area_km2:.1f} km²",
            details={"area_km2": round(area_km2, 3), "max_area_km2": max_area_km2},
        )

    canonical_dict = {
        "type": gtype,
        "coordinates": _round_coords(geojson_geom["coordinates"], precision=7),
    }
    canon_bytes = canonical_json_bytes(canonical_dict)
    geometry_sha256 = sha256_hex(canon_bytes)
    if project_id:
        revision_id = sha256_hex(f"{project_id}:{geometry_sha256}".encode())
    else:
        revision_id = geometry_sha256
    return geom, canon_bytes.decode("utf-8"), revision_id
