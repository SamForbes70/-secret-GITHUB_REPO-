"""Unit tests for local corrections loader, schema validation, and idempotent application (S1.T4)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
import yaml

from maps4u.core.config import Settings
from maps4u.core.errors import E_CORRECTIONS_INVALID, Maps4UError
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch, load_features_from_extract
from maps4u.geo.corrections import apply_corrections


def test_apply_valid_corrections_rename_reclass_add_remove(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    bbox = BBox(
        min_lon=153.085,
        min_lat=-26.660,
        max_lon=153.105,
        max_lat=-26.645,
    )
    extract = get_or_fetch(
        bbox=bbox,
        classes=["roads", "water", "parks", "boundaries", "places", "landmarks"],
        settings=test_settings,
    )
    original_features = load_features_from_extract(extract)

    corr_data = {
        "author": "David",
        "date": "2026-10-21",
        "version": "1.0",
        "corrections": [
            {
                "feature": "road",
                "osm_id": 9002,
                "action": "rename",
                "name": "The Esplanade",
                "expected_name": "First Avenue",
            },
            {
                "feature": "road",
                "osm_id": 9001,
                "action": "reclass",
                "new_class": "highway",
            },
            {
                "feature": "park",
                "osm_id": 9005,
                "action": "remove",
            },
            {
                "feature": "place",
                "lat": -26.6525,
                "lon": 153.0965,
                "action": "add",
                "name": "Sunshine Beach Headland",
                "type": "landmark",
            },
        ],
    }
    corr_file = tmp_path / "corrections.yaml"
    corr_file.write_text(yaml.safe_dump(corr_data), encoding="utf-8")

    updated_1, warnings_1 = apply_corrections(original_features, corr_file)
    assert warnings_1 == []

    disk_roads = gpd.read_file(extract.gpkg_path, layer="roads")
    assert "First Avenue" in set(disk_roads["name"].tolist())
    assert int(disk_roads["corrected"].sum()) == 0

    road_9002 = updated_1.roads[updated_1.roads["osm_id"] == 9002].iloc[0]
    assert road_9002["name"] == "The Esplanade"
    assert road_9002["corrected"] == 1

    road_9001 = updated_1.roads[updated_1.roads["osm_id"] == 9001].iloc[0]
    assert road_9001["maps4u_class"] == "highway"
    assert road_9001["corrected"] == 1

    assert len(updated_1.parks) == 0
    assert "Sunshine Beach Headland" in set(updated_1.places["name"].tolist())

    updated_2, _ = apply_corrections(original_features, corr_file)
    assert updated_1.roads["name"].tolist() == updated_2.roads["name"].tolist()
    assert len(updated_1.places) == len(updated_2.places)


def test_corrections_unknown_osm_id_and_stale_target_warnings(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    bbox = BBox(
        min_lon=153.085,
        min_lat=-26.660,
        max_lon=153.105,
        max_lat=-26.645,
    )
    extract = get_or_fetch(bbox=bbox, classes=["roads"], settings=test_settings)
    features = load_features_from_extract(extract)

    corr_data = {
        "corrections": [
            {
                "feature": "road",
                "osm_id": 99999999,
                "action": "rename",
                "name": "Ghost Street",
            },
            {
                "feature": "road",
                "osm_id": 9002,
                "action": "rename",
                "expected_name": "Old Upstream Name",
                "name": "New Street Name",
            },
        ]
    }
    corr_file = tmp_path / "stale_and_unknown.yaml"
    corr_file.write_text(yaml.safe_dump(corr_data), encoding="utf-8")
    updated, warnings = apply_corrections(features, corr_file)
    codes = {w.code for w in warnings}
    assert "W_CORRECTION_TARGET_MISSING" in codes
    assert "W_CORRECTION_STALE_TARGET" in codes
    road_9002 = updated.roads[updated.roads["osm_id"] == 9002].iloc[0]
    assert road_9002["name"] == "New Street Name"


def test_corrections_invalid_yaml_or_schema_raises(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    bbox = BBox(
        min_lon=153.085,
        min_lat=-26.660,
        max_lon=153.105,
        max_lat=-26.645,
    )
    extract = get_or_fetch(bbox=bbox, classes=["roads"], settings=test_settings)
    features = load_features_from_extract(extract)

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("corrections: [unclosed", encoding="utf-8")
    with pytest.raises(Maps4UError) as exc1:
        apply_corrections(features, bad_yaml)
    assert exc1.value.code == E_CORRECTIONS_INVALID

    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text(
        yaml.safe_dump(
            {
                "corrections": [
                    {
                        "feature": "invalid_layer",
                        "action": "explode",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Maps4UError) as exc2:
        apply_corrections(features, bad_schema)
    assert exc2.value.code == E_CORRECTIONS_INVALID
