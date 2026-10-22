"""Job lifecycle state machine (§6.1) with governed output enforcement."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maps4u.core.errors import E_GOVERNED_OUTPUT_MISSING, E_NOT_FOUND, E_STATE_ILLEGAL, Maps4UError
from maps4u.core.logging import append_audit_jsonl

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "created": {"validating", "failed"},
    "validating": {"queued", "failed"},
    "queued": {"assessing", "failed"},
    "assessing": {"acquiring", "failed"},
    "acquiring": {"transforming", "failed"},
    "transforming": {"styling", "failed"},
    "styling": {"labelling", "failed"},
    "labelling": {"composing", "failed"},
    "composing": {"rendering", "failed"},
    "rendering": {"verifying", "failed"},
    "verifying": {"proof_ready", "failed"},
    "proof_ready": {"finalized", "rejected", "failed"},
    "rejected": set(),
    "finalized": set(),
    "failed": {"queued"},
}

GOVERNED_OUTPUT_FILES = ("proof.pdf", "thumb.png", "qa-report.md", "qa-report.json", "manifest.json")


def verify_governed_outputs(artifact_dir: Path, job_id: str) -> list[str]:
    """Return any missing governed output filenames for job_id."""
    job_dir = artifact_dir / job_id
    missing: list[str] = []
    for name in GOVERNED_OUTPUT_FILES:
        path = job_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def transition_job_state(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    target_state: str,
    stage: str,
    event: str,
    data_dir: Path,
    artifact_dir: Path | None = None,
    payload: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> str:
    """Transition job to target_state, enforcing state rules and governed outputs."""
    row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)

    current_state = str(row["status"])
    allowed = LEGAL_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise Maps4UError(
            E_STATE_ILLEGAL,
            f"Illegal state transition for job {job_id}: {current_state} -> {target_state}",
            details={"job_id": job_id, "from": current_state, "to": target_state},
            status_code=409,
        )

    if target_state == "proof_ready":
        if artifact_dir is None:
            raise Maps4UError(
                E_GOVERNED_OUTPUT_MISSING,
                "Cannot transition to proof_ready without artifact_dir verification",
                status_code=409,
            )
        missing = verify_governed_outputs(artifact_dir, job_id)
        if missing:
            raise Maps4UError(
                E_GOVERNED_OUTPUT_MISSING,
                f"Cannot transition {job_id} to proof_ready; missing governed outputs: {missing}",
                details={"job_id": job_id, "missing": missing},
                status_code=409,
            )

    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE jobs SET status = ?, error_code = ?, error_detail = ?, updated_at = ? WHERE job_id = ?",
        (target_state, error_code, error_detail, now, job_id),
    )
    payload_str = json.dumps(payload or {}, sort_keys=True)
    conn.execute(
        "INSERT INTO job_events (job_id, ts, stage, event, payload_json) VALUES (?, ?, ?, ?, ?)",
        (job_id, now, stage, event, payload_str),
    )
    append_audit_jsonl(
        data_dir,
        {
            "ts": now,
            "job_id": job_id,
            "stage": stage,
            "event": event,
            "from_state": current_state,
            "to_state": target_state,
            "payload": payload or {},
        },
    )
    return target_state
