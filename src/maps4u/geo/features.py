"""FeatureSet container and GeoPackage layer schema definitions (§5.3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

LAYER_COLUMNS: dict[str, list[str]] = {
    "roads": [
        "osm_id",
        "name",
        "ref",
        "highway",
        "oneway",
        "surface",
        "z_order_base",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "water": [
        "osm_id",
        "name",
        "water_type",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "water_lines": [
        "osm_id",
        "name",
        "waterway",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "parks": [
        "osm_id",
        "name",
        "park_type",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "boundaries": [
        "osm_id",
        "name",
        "admin_level",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "coastline": [
        "osm_id",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "places": [
        "osm_id",
        "name",
        "place_type",
        "importance",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
    "landmarks": [
        "osm_id",
        "name",
        "landmark_type",
        "maps4u_class",
        "corrected",
        "correction_id",
        "geometry",
    ],
}

ALL_LAYERS = tuple(LAYER_COLUMNS.keys())


def empty_layer_gdf(layer: str) -> gpd.GeoDataFrame:
    cols = LAYER_COLUMNS[layer]
    data: dict[str, Any] = {c: pd.Series(dtype="object") for c in cols if c != "geometry"}
    if "osm_id" in data:
        data["osm_id"] = pd.Series(dtype="int64")
    if "corrected" in data:
        data["corrected"] = pd.Series(dtype="int64")
    if "z_order_base" in data:
        data["z_order_base"] = pd.Series(dtype="int64")
    if "importance" in data:
        data["importance"] = pd.Series(dtype="int64")
    return gpd.GeoDataFrame(data, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326")


@dataclass
class OsmExtract:
    """Provenance-linked cached OSM extract (§7.2)."""

    snapshot_id: str
    bbox_str: str
    raw_path: Path
    gpkg_path: Path
    query: str
    source_url: str
    source_ts: str
    osm_base_date: str | None
    sha256: str
    feature_counts: dict[str, int]
    cache_hit: bool = False


@dataclass
class FeatureSet:
    """In-memory working copy of all cartographic feature layers."""

    roads: gpd.GeoDataFrame
    water: gpd.GeoDataFrame
    water_lines: gpd.GeoDataFrame
    parks: gpd.GeoDataFrame
    boundaries: gpd.GeoDataFrame
    coastline: gpd.GeoDataFrame
    places: gpd.GeoDataFrame
    landmarks: gpd.GeoDataFrame

    def copy(self) -> FeatureSet:
        return FeatureSet(
            roads=self.roads.copy(deep=True),
            water=self.water.copy(deep=True),
            water_lines=self.water_lines.copy(deep=True),
            parks=self.parks.copy(deep=True),
            boundaries=self.boundaries.copy(deep=True),
            coastline=self.coastline.copy(deep=True),
            places=self.places.copy(deep=True),
            landmarks=self.landmarks.copy(deep=True),
        )

    def get_layer(self, layer_name: str) -> gpd.GeoDataFrame:
        return getattr(self, layer_name)

    def set_layer(self, layer_name: str, gdf: gpd.GeoDataFrame) -> None:
        setattr(self, layer_name, gdf)
