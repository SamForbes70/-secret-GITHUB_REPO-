"""Immutable GeoPackage snapshot storage, cache lookup separation, and corruption recovery (§5.3, §5.8, DATA-001, DATA-003)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import geopandas as gpd

from maps4u.core.db import db_session, run_migrations
from maps4u.core.errors import E_STORAGE, Maps4UError
from maps4u.core.ids import sha256_hex
from maps4u.core.models import BBox
from maps4u.geo.features import ALL_LAYERS, FeatureSet, OsmExtract
from maps4u.geo.fetch import parse_overpass_bytes


def compute_cache_lookup_key(bbox: BBox, query: str) -> str:
    """Compute deterministic cache lookup identity for (bbox, query) independent of content."""
    query_hash = sha256_hex(query)
    return sha256_hex(f"{bbox.to_string(6)}:{query_hash}")


def compute_snapshot_id(bbox: BBox, query: str, raw_sha256: str | None = None) -> str:
    """Compute immutable content-addressed snapshot ID when raw_sha256 is provided, or lookup key otherwise (DATA-001)."""
    lookup_key = compute_cache_lookup_key(bbox, query)
    if raw_sha256:
        return sha256_hex(f"{lookup_key}:{raw_sha256}")
    return lookup_key


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


def read_geopackage_snapshot(
    gpkg_path: Path,
    *,
    raw_fallback_path: Path | None = None,
    expected_raw_sha256: str | None = None,
) -> FeatureSet:
    """Read all 8 layers from GeoPackage; recover from raw JSON or fail diagnostically (DATA-003)."""
    layers: dict[str, gpd.GeoDataFrame] = {}
    corrupted_error: Exception | None = None
    corrupted_layer: str | None = None

    if not gpkg_path.is_file():
        corrupted_error = FileNotFoundError(f"GeoPackage file missing: {gpkg_path}")
        corrupted_layer = ALL_LAYERS[0]
    else:
        for layer_name in ALL_LAYERS:
            try:
                layers[layer_name] = gpd.read_file(gpkg_path, layer=layer_name)
            except Exception as exc:
                corrupted_error = exc
                corrupted_layer = layer_name
                break

    if corrupted_error is None:
        return FeatureSet(**layers)

    candidate_raw = raw_fallback_path
    if candidate_raw is None:
        inferred_raw = gpkg_path.with_suffix(".raw.json")
        if inferred_raw.is_file():
            candidate_raw = inferred_raw

    if candidate_raw is not None and candidate_raw.is_file():
        try:
            raw_bytes = candidate_raw.read_bytes()
            if expected_raw_sha256 and sha256_hex(raw_bytes) != expected_raw_sha256:
                raise ValueError("Immutable raw JSON SHA-256 mismatch during GeoPackage recovery")
            recovered_features, _ = parse_overpass_bytes(raw_bytes)
            write_geopackage_snapshot(gpkg_path, recovered_features)
            reverified: dict[str, gpd.GeoDataFrame] = {}
            for layer_name in ALL_LAYERS:
                reverified[layer_name] = gpd.read_file(gpkg_path, layer=layer_name)
            return FeatureSet(**reverified)
        except Exception as rec_exc:
            raise Maps4UError(
                E_STORAGE,
                f"Corrupted GeoPackage {gpkg_path.name!r} (layer {corrupted_layer!r}: {corrupted_error}) "
                f"and recovery from raw snapshot failed: {rec_exc}",
                details={
                    "gpkg_path": str(gpkg_path),
                    "layer": corrupted_layer,
                    "error": str(corrupted_error),
                    "recovery_error": str(rec_exc),
                },
                status_code=422,
            ) from rec_exc

    raise Maps4UError(
        E_STORAGE,
        f"Corrupted or unreadable GeoPackage {gpkg_path.name!r} at layer {corrupted_layer!r}: {corrupted_error}",
        details={
            "gpkg_path": str(gpkg_path),
            "layer": corrupted_layer,
            "error": str(corrupted_error),
        },
        status_code=422,
    ) from corrupted_error


load_features_from_gpkg = read_geopackage_snapshot


def record_snapshot_in_db(db_path: Path, extract: OsmExtract, *, lookup_key: str | None = None) -> None:
    """Persist immutable snapshot record without overwriting historical snapshots (DATA-001)."""
    run_migrations(db_path)
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO osm_snapshots (
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
    if lookup_key:
        index_path = extract.gpkg_path.parent / f"{lookup_key}.latest.json"
        index_path.write_text(
            json.dumps(
                {
                    "lookup_key": lookup_key,
                    "snapshot_id": extract.snapshot_id,
                    "sha256": extract.sha256,
                    "fetched_at": extract.source_ts,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def _is_snapshot_expired(fetched_at_iso: str, max_age_days: int | None) -> bool:
    if max_age_days is None or max_age_days == 0:
        return False
    if max_age_days < 0:
        return True
    try:
        dt = datetime.fromisoformat(fetched_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt) > timedelta(days=int(max_age_days))
    except Exception:
        return True


def lookup_cached_snapshot(
    db_path: Path,
    cache_dir: Path,
    lookup_key: str,
    query: str,
    max_age_days: int | None = None,
) -> OsmExtract | None:
    """Look up the latest unexpired immutable snapshot for lookup_key (DATA-001)."""
    run_migrations(db_path)
    candidate_snapshot_id = lookup_key
    index_path = cache_dir / f"{lookup_key}.latest.json"
    if index_path.is_file():
        try:
            idx_data = json.loads(index_path.read_text(encoding="utf-8"))
            candidate_snapshot_id = str(idx_data.get("snapshot_id") or lookup_key)
        except Exception:
            candidate_snapshot_id = lookup_key

    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM osm_snapshots WHERE snapshot_id = ?", (candidate_snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        fetched_at = str(row["fetched_at"])
        if _is_snapshot_expired(fetched_at, max_age_days):
            return None
        gpkg_path = Path(str(row["gpkg_path"]))
        raw_path = Path(str(row["raw_path"]))
        if not gpkg_path.is_file() or not raw_path.is_file():
            return None
        expected_sha = str(row["sha256"])
        actual_sha = sha256_hex(raw_path.read_bytes())
        if actual_sha != expected_sha:
            return None
        return OsmExtract(
            snapshot_id=str(row["snapshot_id"]),
            bbox_str=str(row["bbox"]),
            raw_path=raw_path,
            gpkg_path=gpkg_path,
            query=query,
            source_url=str(row["source_url"]),
            source_ts=fetched_at,
            osm_base_date=row["osm_base_date"],
            sha256=expected_sha,
            feature_counts=json.loads(row["feature_counts_json"] or "{}"),
            cache_hit=True,
        )


def purge_expired_unreferenced_snapshots(
    *,
    db_path: Path,
    cache_dir: Path,
    artifact_dir: Path | None = None,
    max_age_days: int = 30,
    dry_run: bool = True,
) -> dict[str, object]:
    """Purge expired OSM cache snapshots not referenced by any job or bundle manifest (R-14, OD-8)."""
    run_migrations(db_path)
    referenced_ids: set[str] = set()

    with db_session(db_path) as conn:
        bundle_rows = conn.execute("SELECT manifest_json FROM bundles").fetchall()
        for r in bundle_rows:
            try:
                mf = json.loads(str(r["manifest_json"] or "{}"))
                snap_id = str(
                    mf.get("provenance", {}).get("snapshot_id")
                    or mf.get("inputs", {}).get("osm_snapshot_id")
                    or ""
                )
                if snap_id:
                    referenced_ids.add(snap_id)
            except Exception:
                continue
        event_rows = conn.execute(
            "SELECT payload_json FROM job_events WHERE payload_json IS NOT NULL AND payload_json LIKE '%snapshot_id%'"
        ).fetchall()
        for r in event_rows:
            try:
                ev = json.loads(str(r["payload_json"] or "{}"))
                snap_id = str(ev.get("snapshot_id") or "")
                if snap_id:
                    referenced_ids.add(snap_id)
            except Exception:
                continue

    if artifact_dir is not None and artifact_dir.is_dir():
        for mf_path in artifact_dir.glob("*/manifest.json"):
            try:
                mf = json.loads(mf_path.read_text(encoding="utf-8"))
                snap_id = str(
                    mf.get("provenance", {}).get("snapshot_id")
                    or mf.get("inputs", {}).get("osm_snapshot_id")
                    or ""
                )
                if snap_id:
                    referenced_ids.add(snap_id)
            except Exception:
                continue

    protected_referenced_ids: list[str] = []
    protected_unexpired_ids: list[str] = []
    purged_snapshot_ids: list[str] = []
    freed_bytes = 0

    with db_session(db_path) as conn:
        snap_rows = conn.execute("SELECT * FROM osm_snapshots ORDER BY fetched_at ASC").fetchall()
        for row in snap_rows:
            snap_id = str(row["snapshot_id"])
            fetched_at = str(row["fetched_at"])
            if snap_id in referenced_ids:
                protected_referenced_ids.append(snap_id)
                continue
            if not _is_snapshot_expired(fetched_at, max_age_days):
                protected_unexpired_ids.append(snap_id)
                continue

            purged_snapshot_ids.append(snap_id)
            for p_str in (row["raw_path"], row["gpkg_path"]):
                if p_str:
                    p = Path(str(p_str))
                    if p.is_file():
                        freed_bytes += p.stat().st_size
                        if not dry_run:
                            p.unlink(missing_ok=True)
            if not dry_run:
                conn.execute("DELETE FROM osm_snapshots WHERE snapshot_id = ?", (snap_id,))

        remaining_ids = {
            str(r["snapshot_id"])
            for r in conn.execute("SELECT snapshot_id FROM osm_snapshots").fetchall()
        }

    purged_set = set(purged_snapshot_ids)
    removed_pointers: list[str] = []
    if cache_dir.is_dir():
        for ptr_path in sorted(cache_dir.glob("*.latest.json")):
            try:
                ptr_data = json.loads(ptr_path.read_text(encoding="utf-8"))
                target_snap = str(ptr_data.get("snapshot_id") or "")
            except Exception:
                target_snap = ""
            if target_snap in purged_set or (target_snap and target_snap not in remaining_ids):
                removed_pointers.append(ptr_path.name)
                if not dry_run:
                    ptr_path.unlink(missing_ok=True)

    return {
        "dry_run": dry_run,
        "max_age_days": max_age_days,
        "purged_snapshot_ids": purged_snapshot_ids,
        "protected_referenced_ids": protected_referenced_ids,
        "protected_unexpired_ids": protected_unexpired_ids,
        "removed_pointers": removed_pointers,
        "freed_bytes": freed_bytes,
    }
