from __future__ import annotations

import geopandas as gpd

from maps4u.core.config import Settings
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch


def test_fetch_roads_inside_bounding_box_and_cache(test_settings: Settings) -> None:
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    extract = get_or_fetch(bbox=bbox, classes=["roads"], settings=test_settings)
    assert extract.gpkg_path.is_file()
    assert extract.raw_path.is_file()
    assert extract.osm_base_date == "2026-07-01T00:00:00Z"
    assert len(extract.sha256) == 64
    assert extract.feature_counts["roads"] == 2
    roads_gdf = gpd.read_file(extract.gpkg_path, layer="roads")
    assert len(roads_gdf) == 2
    assert set(roads_gdf["name"].tolist()) == {"Aerodrome Road", "First Avenue"}
    assert "maps4u_class" in roads_gdf.columns
    assert "corrected" in roads_gdf.columns
    extract_cached = get_or_fetch(bbox=bbox, classes=["roads"], settings=test_settings)
    assert extract_cached.snapshot_id == extract.snapshot_id
    assert extract_cached.cache_hit is True
