"""Client corrections file loader, schema validator, and idempotent applier (§5.6 & §6.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import jsonschema
import pandas as pd
import yaml
from shapely.geometry import LineString, Point

from maps4u.core.config import resolve_resource_path
from maps4u.core.errors import E_CORRECTIONS_INVALID, Maps4UError
from maps4u.core.ids import sha256_hex
from maps4u.geo.features import FeatureSet

FEATURE_TO_LAYER: dict[str, str] = {
    "road": "roads",
    "water": "water",
    "water_line": "water_lines",
    "park": "parks",
    "boundary": "boundaries",
    "place": "places",
    "landmark": "landmarks",
}

SCHEMA_PATH = resolve_resource_path("schemas/corrections.schema.json")


@dataclass(frozen=True)
class CorrectionWarning:
    code: str
    message: str
    item: dict[str, Any]


def _load_and_validate_corrections(
    corrections_path: Path, schema_path: Path = SCHEMA_PATH
) -> tuple[dict[str, Any], str]:
    if not corrections_path.is_file():
        raise Maps4UError(E_CORRECTIONS_INVALID, f"Corrections file not found: {corrections_path}")
    raw_bytes = corrections_path.read_bytes()
    if len(raw_bytes) > 1_048_576:
        raise Maps4UError(E_CORRECTIONS_INVALID, "Corrections file exceeds 1 MB limit")
    corr_id = sha256_hex(raw_bytes)[:16]

    try:
        data = yaml.safe_load(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise Maps4UError(E_CORRECTIONS_INVALID, f"Invalid YAML in corrections file: {exc}") from exc

    if not isinstance(data, dict):
        raise Maps4UError(E_CORRECTIONS_INVALID, "Corrections root must be a YAML mapping")

    resolved_schema = schema_path if schema_path.is_file() else resolve_resource_path("schemas/corrections.schema.json")
    schema = json.loads(resolved_schema.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise Maps4UError(
            E_CORRECTIONS_INVALID,
            f"Corrections schema validation failed: {exc.message}",
        ) from exc

    return data, corr_id


load_and_validate_corrections = _load_and_validate_corrections


def resolve_safe_corrections_path(
    corrections_ref: str,
    data_dir: Path,
    artifact_dir: Path,
    conn: Any | None = None,
) -> Path:
    """Resolve a user-supplied corrections_ref safely, blocking arbitrary file access (BUG-003)."""
    ref_str = corrections_ref.strip()
    if not ref_str:
        raise Maps4UError(E_CORRECTIONS_INVALID, "Empty corrections_ref", status_code=422)

    if conn is not None:
        row = conn.execute(
            "SELECT path FROM corrections_files WHERE corrections_id = ?",
            (ref_str,),
        ).fetchone()
        if row is not None:
            ref_str = str(row["path"])

    if ".." in Path(ref_str).parts:
        raise Maps4UError(
            E_CORRECTIONS_INVALID,
            f"Invalid corrections_ref {corrections_ref!r}: path traversal is forbidden",
            status_code=422,
        )

    candidate = Path(ref_str)
    if not candidate.is_absolute():
        candidate = (data_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = (data_dir.resolve(), artifact_dir.resolve())
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise Maps4UError(
            E_CORRECTIONS_INVALID,
            f"Forbidden corrections_ref {corrections_ref!r}: must reside within governed data_dir",
            status_code=422,
        )
    if not candidate.is_file():
        raise Maps4UError(
            E_CORRECTIONS_INVALID,
            f"Corrections file not found within governed storage: {corrections_ref!r}",
            status_code=422,
        )
    return candidate


def apply_corrections(
    features: FeatureSet,
    corrections_path: Path,
    schema_path: Path = SCHEMA_PATH,
) -> tuple[FeatureSet, list[CorrectionWarning]]:
    """Apply corrections to a working copy of FeatureSet without mutating the source extract."""
    payload, corr_id = _load_and_validate_corrections(corrections_path, schema_path=schema_path)
    working = features.copy()
    warnings: list[CorrectionWarning] = []

    for idx, item in enumerate(payload.get("corrections", [])):
        feat_type = str(item["feature"])
        action = str(item["action"])
        layer_name = FEATURE_TO_LAYER[feat_type]
        gdf = working.get_layer(layer_name)
        item_corr_id = f"{corr_id}:{idx}"

        if action in ("rename", "remove", "reclass"):
            if "osm_id" not in item:
                raise Maps4UError(E_CORRECTIONS_INVALID, f"Action {action!r} requires osm_id")
            target_id = int(item["osm_id"])
            mask = gdf["osm_id"] == target_id
            if not bool(mask.any()):
                warnings.append(
                    CorrectionWarning(
                        code="W_CORRECTION_TARGET_MISSING",
                        message=f"Target osm_id={target_id} not found in layer {layer_name}",
                        item=item,
                    )
                )
                continue

            expected_name = item.get("expected_name")
            if expected_name is not None and "name" in gdf.columns:
                current_names = set(gdf.loc[mask, "name"].dropna().astype(str).tolist())
                if expected_name not in current_names and item.get("name") not in current_names:
                    warnings.append(
                        CorrectionWarning(
                            code="W_CORRECTION_STALE_TARGET",
                            message=f"Target osm_id={target_id} upstream name {current_names} != expected {expected_name!r}",
                            item=item,
                        )
                    )

            if action == "rename":
                new_name = str(item.get("name", ""))
                gdf.loc[mask, "name"] = new_name
                gdf.loc[mask, "corrected"] = 1
                gdf.loc[mask, "correction_id"] = item_corr_id
            elif action == "reclass":
                new_class = str(item.get("new_class") or item.get("type") or "local")
                gdf.loc[mask, "maps4u_class"] = new_class
                gdf.loc[mask, "corrected"] = 1
                gdf.loc[mask, "correction_id"] = item_corr_id
            elif action == "remove":
                gdf = gdf.loc[~mask].reset_index(drop=True)
                working.set_layer(layer_name, gdf)

        elif action == "add":
            synthetic_id = int(item.get("osm_id") or -(idx + 1))
            if not gdf.empty and bool((gdf["osm_id"] == synthetic_id).any()):
                gdf = gdf.loc[gdf["osm_id"] != synthetic_id].reset_index(drop=True)

            if layer_name in ("places", "landmarks"):
                if "lat" not in item or "lon" not in item:
                    raise Maps4UError(E_CORRECTIONS_INVALID, "Adding a place/landmark requires lat and lon")
                geom = Point(float(item["lon"]), float(item["lat"]))
                new_row: dict[str, Any] = {
                    "osm_id": synthetic_id,
                    "name": item.get("name"),
                    "maps4u_class": str(item.get("type") or feat_type),
                    "corrected": 1,
                    "correction_id": item_corr_id,
                    "geometry": geom,
                }
                if layer_name == "places":
                    new_row["place_type"] = str(item.get("type") or "landmark")
                    new_row["importance"] = 80
                else:
                    new_row["landmark_type"] = str(item.get("type") or "landmark")
            else:
                coords = item.get("coordinates")
                if not coords or len(coords) < 2:
                    raise Maps4UError(E_CORRECTIONS_INVALID, f"Adding {feat_type} requires coordinates")
                geom = LineString([(float(c[0]), float(c[1])) for c in coords])
                new_row = {
                    "osm_id": synthetic_id,
                    "name": item.get("name"),
                    "ref": None,
                    "highway": str(item.get("highway") or "residential"),
                    "oneway": "no",
                    "surface": None,
                    "z_order_base": 10,
                    "maps4u_class": str(item.get("new_class") or "local"),
                    "corrected": 1,
                    "correction_id": item_corr_id,
                    "geometry": geom,
                }

            add_gdf = gpd.GeoDataFrame([new_row], columns=list(gdf.columns), geometry="geometry", crs="EPSG:4326")
            merged = gpd.GeoDataFrame(pd.concat([gdf, add_gdf], ignore_index=True), geometry="geometry", crs="EPSG:4326")
            working.set_layer(layer_name, merged)

    return working, warnings
