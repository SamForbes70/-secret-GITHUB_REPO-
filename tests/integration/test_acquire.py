"""Integration tests for OSM acquisition, GeoPackage cache, provenance, and retries (S1.T3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_OVERPASS_UNAVAILABLE, Maps4UError
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch, load_features_from_extract
from maps4u.geo.overpass import OverpassClient, build_overpass_query


def test_build_overpass_query_normalises_bbox() -> None:
    bbox = BBox(min_lon=153.0850004, min_lat=-26.6600004, max_lon=153.1050004, max_lat=-26.6450004)
    query = build_overpass_query(bbox, ["roads", "water"])
    assert "-26.660000,153.085000,-26.645000,153.105000" in query
    assert '"highway"' in query
    assert '"natural"="water"' in query


def test_full_acquire_all_layers_and_reload(test_settings: Settings) -> None:
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=test_settings)

    assert extract.cache_hit is False
    assert extract.gpkg_path.is_file()
    assert extract.raw_path.is_file()
    assert extract.osm_base_date == "2026-07-01T00:00:00Z"
    assert extract.feature_counts["roads"] == 2
    assert extract.feature_counts["water"] == 1
    assert extract.feature_counts["water_lines"] == 1
    assert extract.feature_counts["parks"] == 1
    assert extract.feature_counts["boundaries"] == 1
    assert extract.feature_counts["coastline"] == 1
    assert extract.feature_counts["places"] == 1
    assert extract.feature_counts["landmarks"] == 1

    # Check SQLite snapshot provenance record
    with db_session(test_settings.db_path) as conn:
        row = conn.execute(
            "SELECT * FROM osm_snapshots WHERE snapshot_id = ?", (extract.snapshot_id,)
        ).fetchone()
        assert row is not None
        assert row["osm_base_date"] == "2026-07-01T00:00:00Z"
        assert row["sha256"] == extract.sha256

    # Reload FeatureSet from GeoPackage
    fset = load_features_from_extract(extract)
    assert len(fset.roads) == 2
    assert len(fset.water) == 1
    assert len(fset.parks) == 1
    assert len(fset.places) == 1


def test_overpass_retry_ladder_on_failure(tmp_path: Path) -> None:
    attempts = 0

    def failing_transport(url: str, query: str) -> bytes:
        nonlocal attempts
        attempts += 1
        raise OSError("Simulated Overpass timeout")

    sleep_calls: list[float] = []
    client = OverpassClient(
        endpoint_url="https://overpass-api.de/api/interpreter",
        retry_backoff=(0.01, 0.02, 0.03),
        transport=failing_transport,
        sleep_fn=lambda s: sleep_calls.append(s),
    )
    with pytest.raises(Maps4UError) as exc_info:
        client.fetch_raw("[out:json];node(1);out;")
    assert exc_info.value.code == E_OVERPASS_UNAVAILABLE
    assert attempts == 3
    assert len(sleep_calls) == 2
