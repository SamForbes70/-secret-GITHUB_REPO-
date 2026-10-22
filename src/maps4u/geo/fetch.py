"""Overpass response parser and feature classifier (§5.3 & §6.4)."""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
from shapely.validation import make_valid

from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.geo.features import LAYER_COLUMNS, FeatureSet, OsmExtract, empty_layer_gdf

HIGHWAY_CLASS_MAP: dict[str, tuple[str, int]] = {
    "motorway": ("motorway", 20),
    "motorway_link": ("motorway", 19),
    "trunk": ("arterial", 18),
    "trunk_link": ("arterial", 17),
    "primary": ("arterial", 16),
    "primary_link": ("arterial", 15),
    "secondary": ("collector", 14),
    "secondary_link": ("collector", 13),
    "tertiary": ("collector", 12),
    "tertiary_link": ("collector", 11),
    "residential": ("local", 10),
    "unclassified": ("local", 9),
    "living_street": ("local", 8),
    "service": ("service", 5),
    "track": ("service", 4),
    "path": ("path", 3),
    "footway": ("path", 2),
    "cycleway": ("path", 2),
}

PLACE_IMPORTANCE: dict[str, int] = {
    "town": 100,
    "suburb": 90,
    "locality": 70,
    "hamlet": 60,
}


def _way_coords(way: dict[str, Any], nodes_by_id: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
    if "geometry" in way and isinstance(way["geometry"], list):
        return [(float(pt["lon"]), float(pt["lat"])) for pt in way["geometry"] if "lon" in pt and "lat" in pt]
    coords: list[tuple[float, float]] = []
    for nid in way.get("nodes", []):
        if int(nid) in nodes_by_id:
            coords.append(nodes_by_id[int(nid)])
    return coords


def _build_gdf(layer: str, rows: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    if not rows:
        return empty_layer_gdf(layer)
    rows_sorted = sorted(rows, key=lambda r: int(r["osm_id"]))
    cols = LAYER_COLUMNS[layer]
    gdf = gpd.GeoDataFrame(rows_sorted, columns=cols, geometry="geometry", crs="EPSG:4326")
    return gdf


def parse_overpass_bytes(raw_bytes: bytes) -> tuple[FeatureSet, str | None]:
    """Parse raw Overpass JSON bytes into a validated FeatureSet and extract osm_base_date."""
    payload = json.loads(raw_bytes.decode("utf-8"))
    osm_base_date: str | None = payload.get("osm3s", {}).get("timestamp_osm_base")
    elements: list[dict[str, Any]] = payload.get("elements", [])

    nodes_by_id: dict[int, tuple[float, float]] = {}
    for el in elements:
        if el.get("type") == "node" and "lat" in el and "lon" in el:
            nodes_by_id[int(el["id"])] = (float(el["lon"]), float(el["lat"]))

    roads_rows: list[dict[str, Any]] = []
    water_rows: list[dict[str, Any]] = []
    water_lines_rows: list[dict[str, Any]] = []
    parks_rows: list[dict[str, Any]] = []
    boundaries_rows: list[dict[str, Any]] = []
    coastline_rows: list[dict[str, Any]] = []
    places_rows: list[dict[str, Any]] = []
    landmarks_rows: list[dict[str, Any]] = []

    for el in elements:
        etype = el.get("type")
        osm_id = int(el.get("id", 0))
        tags: dict[str, Any] = el.get("tags") or {}
        if not tags:
            continue

        if etype == "node" and osm_id in nodes_by_id:
            lon, lat = nodes_by_id[osm_id]
            pt = Point(lon, lat)
            if "place" in tags or "tourism" in tags or tags.get("natural") in ("peak", "cape"):
                ptype = str(tags.get("place") or tags.get("tourism") or tags.get("natural"))
                places_rows.append(
                    {
                        "osm_id": osm_id,
                        "name": tags.get("name"),
                        "place_type": ptype,
                        "importance": PLACE_IMPORTANCE.get(ptype, 50),
                        "maps4u_class": "suburb" if ptype == "suburb" else "place",
                        "corrected": 0,
                        "correction_id": None,
                        "geometry": pt,
                    }
                )
            if "man_made" in tags or "historic" in tags:
                ltype = str(tags.get("man_made") or tags.get("historic"))
                landmarks_rows.append(
                    {
                        "osm_id": osm_id,
                        "name": tags.get("name"),
                        "landmark_type": ltype,
                        "maps4u_class": "landmark",
                        "corrected": 0,
                        "correction_id": None,
                        "geometry": pt,
                    }
                )

        elif etype == "way":
            coords = _way_coords(el, nodes_by_id)
            if len(coords) < 2:
                continue

            if "highway" in tags:
                hw = str(tags["highway"])
                mclass, z_base = HIGHWAY_CLASS_MAP.get(hw, ("local", 6))
                geom = make_valid(LineString(coords))
                roads_rows.append(
                    {
                        "osm_id": osm_id,
                        "name": tags.get("name"),
                        "ref": tags.get("ref"),
                        "highway": hw,
                        "oneway": tags.get("oneway", "no"),
                        "surface": tags.get("surface"),
                        "z_order_base": z_base,
                        "maps4u_class": mclass,
                        "corrected": 0,
                        "correction_id": None,
                        "geometry": geom,
                    }
                )

            if tags.get("natural") == "water" or tags.get("waterway") == "riverbank" or tags.get("landuse") == "reservoir":
                poly_coords = coords if coords[0] == coords[-1] else [*coords, coords[0]]
                if len(poly_coords) >= 4:
                    water_rows.append(
                        {
                            "osm_id": osm_id,
                            "name": tags.get("name"),
                            "water_type": str(tags.get("water") or tags.get("natural") or "water"),
                            "maps4u_class": "water",
                            "corrected": 0,
                            "correction_id": None,
                            "geometry": make_valid(Polygon(poly_coords)),
                        }
                    )

            if tags.get("waterway") in ("river", "stream", "canal"):
                water_lines_rows.append(
                    {
                        "osm_id": osm_id,
                        "name": tags.get("name"),
                        "waterway": str(tags["waterway"]),
                        "maps4u_class": "water_line",
                        "corrected": 0,
                        "correction_id": None,
                        "geometry": make_valid(LineString(coords)),
                    }
                )

            if tags.get("leisure") in ("park", "nature_reserve") or tags.get("landuse") in ("recreation_ground", "forest"):
                poly_coords = coords if coords[0] == coords[-1] else [*coords, coords[0]]
                if len(poly_coords) >= 4:
                    parks_rows.append(
                        {
                            "osm_id": osm_id,
                            "name": tags.get("name"),
                            "park_type": str(tags.get("leisure") or tags.get("landuse")),
                            "maps4u_class": "park",
                            "corrected": 0,
                            "correction_id": None,
                            "geometry": make_valid(Polygon(poly_coords)),
                        }
                    )

            if tags.get("boundary") == "administrative":
                poly_coords = coords if coords[0] == coords[-1] else [*coords, coords[0]]
                if len(poly_coords) >= 4:
                    boundaries_rows.append(
                        {
                            "osm_id": osm_id,
                            "name": tags.get("name"),
                            "admin_level": str(tags.get("admin_level", "10")),
                            "maps4u_class": "boundary",
                            "corrected": 0,
                            "correction_id": None,
                            "geometry": make_valid(Polygon(poly_coords)),
                        }
                    )

            if tags.get("natural") == "coastline":
                coastline_rows.append(
                    {
                        "osm_id": osm_id,
                        "maps4u_class": "coastline",
                        "corrected": 0,
                        "correction_id": None,
                        "geometry": make_valid(LineString(coords)),
                    }
                )

    fset = FeatureSet(
        roads=_build_gdf("roads", roads_rows),
        water=_build_gdf("water", water_rows),
        water_lines=_build_gdf("water_lines", water_lines_rows),
        parks=_build_gdf("parks", parks_rows),
        boundaries=_build_gdf("boundaries", boundaries_rows),
        coastline=_build_gdf("coastline", coastline_rows),
        places=_build_gdf("places", places_rows),
        landmarks=_build_gdf("landmarks", landmarks_rows),
    )
    return fset, osm_base_date


def fetch_roads_in_bbox(bbox: BBox, settings: Settings) -> OsmExtract:
    """Convenience helper to fetch and cache roads inside a bounding box."""
    from maps4u.geo.acquire import get_or_fetch

    return get_or_fetch(bbox=bbox, classes=["roads"], settings=settings)
