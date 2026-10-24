"""OSM acquisition and immutable content-addressed caching orchestration (§6.4, §7.2, DATA-001, DATA-003)."""

from __future__ import annotations

from datetime import UTC, datetime

from maps4u.core.config import Settings
from maps4u.core.ids import sha256_hex
from maps4u.core.models import BBox
from maps4u.geo.cache import (
    compute_cache_lookup_key,
    compute_snapshot_id,
    lookup_cached_snapshot,
    read_geopackage_snapshot,
    record_snapshot_in_db,
    write_geopackage_snapshot,
)
from maps4u.geo.features import FeatureSet, OsmExtract
from maps4u.geo.fetch import parse_overpass_bytes
from maps4u.geo.overpass import OverpassClient, build_overpass_query


def get_or_fetch(bbox: BBox, classes: list[str], settings: Settings) -> OsmExtract:
    """Fetch or return cached immutable GeoPackage snapshot for bbox and feature classes."""
    settings.ensure_dirs()
    norm_bbox = bbox.normalized(6)
    query = build_overpass_query(norm_bbox, classes, timeout=settings.maps4u_overpass_timeout_s)
    lookup_key = compute_cache_lookup_key(norm_bbox, query)

    cached = lookup_cached_snapshot(
        settings.db_path,
        settings.cache_dir,
        lookup_key,
        query,
        max_age_days=settings.maps4u_cache_max_age_days,
    )
    if cached is not None:
        return cached

    client = OverpassClient(
        endpoint_url=settings.maps4u_overpass_url,
        timeout_s=settings.maps4u_overpass_timeout_s,
        max_concurrency=settings.maps4u_overpass_max_concurrency,
    )
    raw_bytes = client.fetch_raw(query)
    raw_sha256 = sha256_hex(raw_bytes)
    snapshot_id = compute_snapshot_id(norm_bbox, query, raw_sha256)

    raw_path = settings.cache_dir / f"{snapshot_id}.raw.json"
    if not raw_path.is_file():
        raw_path.write_bytes(raw_bytes)

    features, osm_base_date = parse_overpass_bytes(raw_bytes)
    gpkg_path = settings.cache_dir / f"{snapshot_id}.gpkg"
    if not gpkg_path.is_file():
        counts = write_geopackage_snapshot(gpkg_path, features)
    else:
        counts = {name: int(len(features.get_layer(name))) for name in features.__dataclass_fields__}

    extract = OsmExtract(
        snapshot_id=snapshot_id,
        bbox_str=norm_bbox.to_string(6),
        raw_path=raw_path,
        gpkg_path=gpkg_path,
        query=query,
        source_url=settings.maps4u_overpass_url,
        source_ts=datetime.now(UTC).isoformat(),
        osm_base_date=osm_base_date,
        sha256=raw_sha256,
        feature_counts=counts,
        cache_hit=False,
    )
    record_snapshot_in_db(settings.db_path, extract, lookup_key=lookup_key)
    return extract


def load_features_from_extract(extract: OsmExtract) -> FeatureSet:
    """Load a working FeatureSet copy from an OsmExtract GeoPackage with corruption recovery (DATA-003)."""
    return read_geopackage_snapshot(
        extract.gpkg_path,
        raw_fallback_path=extract.raw_path,
        expected_raw_sha256=extract.sha256,
    )
