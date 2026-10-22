"""Provenance manifest generator and governed artifact bundle writer (Stage 4 S4.T3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maps4u.core.ids import canonical_json_bytes, sha256_hex


def write_manifest(
    job_id: str,
    out_dir: Path,
    *,
    spec_id: str,
    snapshot_id: str,
    snapshot_sha256: str,
    osm_base_date: str | None,
    style_ref: str,
    style_sha256: str,
    corrections_sha256: str | None,
    pdf_path: Path,
    thumb_path: Path,
    qa_json_path: Path,
    qa_md_path: Path,
    content_hash: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_data: dict[str, Any] = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "spec_id": spec_id,
        "provenance": {
            "snapshot_id": snapshot_id,
            "snapshot_sha256": snapshot_sha256,
            "osm_base_date": osm_base_date,
            "licence": "ODbL-1.0 (OpenStreetMap contributors)",
            "style_ref": style_ref,
            "style_sha256": style_sha256,
            "corrections_sha256": corrections_sha256,
        },
        "outputs": {
            "proof_pdf": {
                "filename": pdf_path.name,
                "sha256": sha256_hex(pdf_path.read_bytes()),
                "bytes": pdf_path.stat().st_size,
            },
            "thumb_png": {
                "filename": thumb_path.name,
                "sha256": sha256_hex(thumb_path.read_bytes()),
                "bytes": thumb_path.stat().st_size,
            },
            "qa_report_json": {
                "filename": qa_json_path.name,
                "sha256": sha256_hex(qa_json_path.read_bytes()),
                "bytes": qa_json_path.stat().st_size,
            },
            "qa_report_md": {
                "filename": qa_md_path.name,
                "sha256": sha256_hex(qa_md_path.read_bytes()),
                "bytes": qa_md_path.stat().st_size,
            },
            "content_hash": content_hash,
        },
    }
    manifest_data["manifest_sha256"] = sha256_hex(canonical_json_bytes(manifest_data))
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_data
