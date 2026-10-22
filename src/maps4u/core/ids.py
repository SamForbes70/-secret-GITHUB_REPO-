"""Deterministic identifier and hashing utilities."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "area"


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def make_project_id(area_name: str, created_seed: str = "") -> str:
    slug = slugify(area_name)
    digest = sha256_hex(f"{slug}:{created_seed}")[:8]
    return f"proj-{slug}-{digest}"


def make_job_id(area_name: str, yyyymm: str, edition: str = "ed1", suffix: str = "") -> str:
    base = f"{slugify(area_name)}-{slugify(yyyymm)}-{slugify(edition)}"
    if suffix:
        return f"{base}-{suffix}"
    return base


def make_spec_id(spec_payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(spec_payload))


def make_bundle_id(job_id: str, spec_payload: dict[str, Any]) -> str:
    digest = make_spec_id(spec_payload)[:8]
    return f"{job_id}-{digest}"
