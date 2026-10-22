"""GeoPackage snapshot storage and SQLite provenance persistence (§5.3 & §5.8)."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from maps4u.core.db import db_session, run_migrations
from maps4u.core.ids import sha256_hex
from maps4u.core.models import BBox
from maps4u.geo.features import ALL_LAYERS, FeatureSet, OsmExtract, empty_layer_gdf


def compute_snapshot_id(bbox: BBox, query: str) -> str:
    query_hash = sha256_hex(query)
    return sha256_hex(f"{bbox.to_string(6)}:{query_hash}")


def write_geopackage_snapshot(gpkg_path: Path, features: FeatureSet) -> dict[str, int]:
    gpkg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = gpkg_path.with_suffix(".tmp.gpkg")
    if tmp_path.exists():
        tmp_path.unlink()

    counts: dict[str, int] = {}
    for layer_name in ALL_LAYERS:
        gdf = features.get_layer(layer_name)
        counts[layer_name] = int(len(gdf))
        gdf.to_file(tmp_path, layer=layer_name, driver="GPKG")

    tmp_path.replace(gpkg_path)
    return counts


def read_geopackage_snapshot(gpkg_path: Path) -> FeatureSet:
    layers: dict[str, gpd.GeoDataFrame] = {}
    for layer_name in ALL_LAYERS:
        try:
            layers[layer_name] = gpd.read_file(gpkg_path, layer=layer_name)
        except Exception:
            layers[layer_name] = empty_layer_gdf(layer_name)
    return FeatureSet(**layers)


def record_snapshot_in_db(db_path: Path, extract: OsmExtract) -> None:
    run_migrations(db_path)
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO osm_snapshots (
                snapshot_id, bbox, fetched_at, source_url, raw_path, gpkg_path,
                osm_base_date, feature_counts_json, sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extract.snapshot_id,
                extract.bbox_str,
                extract.source_ts,
                extract.source_url,
                str(extract.raw_path),
                str(extract.gpkg_path),
                extract.osm_base_date,
                json.dumps(extract.feature_counts, sort_keys=True),
                extract.sha256,
            ),
        )


def lookup_cached_snapshot(db_path: Path, cache_dir: Path, snapshot_id: str, query: str) -> OsmExtract | None:
    gpkg_path = cache_dir / f"{snapshot_id}.gpkg"
    raw_path = cache_dir / f"{snapshot_id}.raw.json"
    if not gpkg_path.is_file() or not raw_path.is_file():
        return None
    run_migrations(db_path)
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM osm_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        return OsmExtract(
            snapshot_id=snapshot_id,
            bbox_str=str(row["bbox"]),
            raw_path=raw_path,
            gpkg_path=gpkg_path,
            query=query,
            source_url=str(row["source_url"]),
            source_ts=str(row["fetched_at"]),
            osm_base_date=row["osm_base_date"],
            sha256=str(row["sha256"]),
            feature_counts=json.loads(row["feature_counts_json"] or "{}"),
            cache_hit=True,
        )
