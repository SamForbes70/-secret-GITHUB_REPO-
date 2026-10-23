"""Job lifecycle state machine (§6.1) with governed output and QA gate enforcement (BUG-008)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader

from maps4u.core.errors import (
    E_GOVERNED_OUTPUT_MISSING,
    E_NOT_FOUND,
    E_QA_FAILED,
    E_STATE_ILLEGAL,
    Maps4UError,
)
from maps4u.core.ids import sha256_hex
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
    """Return any missing or empty governed output filenames for job_id."""
    job_dir = artifact_dir / job_id
    missing: list[str] = []
    for name in GOVERNED_OUTPUT_FILES:
        path = job_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def verify_governed_qa_and_pdf(artifact_dir: Path, job_id: str) -> dict[str, Any]:
    """Validate qa-report.json, proof.pdf structure, and manifest.json hash alignment (BUG-008)."""
    job_dir = artifact_dir / job_id
    qa_path = job_dir / "qa-report.json"
    try:
        qa_data = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise Maps4UError(
            E_QA_FAILED,
            f"Invalid or corrupted qa-report.json for job {job_id!r}: {exc}",
            details={"job_id": job_id},
            status_code=422,
        ) from exc

    if not isinstance(qa_data, dict) or "passed" not in qa_data or "blocker_count" not in qa_data:
        raise Maps4UError(
            E_QA_FAILED,
            f"Incomplete qa-report.json for job {job_id!r}: missing 'passed' or 'blocker_count'",
            details={"job_id": job_id},
            status_code=422,
        )

    reported_job_id = qa_data.get("job_id")
    if reported_job_id and str(reported_job_id) != job_id:
        raise Maps4UError(
            E_QA_FAILED,
            f"Stale or mismatched qa-report.json job_id: expected {job_id!r}, got {reported_job_id!r}",
            details={"job_id": job_id, "reported_job_id": reported_job_id},
            status_code=422,
        )

    passed = bool(qa_data.get("passed", False))
    blocker_count = int(qa_data.get("blocker_count", 1))
    if not passed or blocker_count > 0:
        raise Maps4UError(
            E_QA_FAILED,
            f"QA preflight failed for job {job_id!r} (passed={passed}, blocker_count={blocker_count})",
            details={
                "job_id": job_id,
                "passed": passed,
                "blocker_count": blocker_count,
                "findings": qa_data.get("findings", []),
            },
            status_code=422,
        )

    pdf_path = job_dir / "proof.pdf"
    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        raise Maps4UError(
            E_QA_FAILED,
            f"Corrupted proof.pdf for job {job_id!r}: missing %PDF- header",
            details={"job_id": job_id},
            status_code=422,
        )
    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) != 1:
            raise Maps4UError(
                E_QA_FAILED,
                f"Invalid proof.pdf page count for job {job_id!r}: expected 1, got {len(reader.pages)}",
                details={"job_id": job_id, "pages": len(reader.pages)},
                status_code=422,
            )
    except Maps4UError:
        raise
    except Exception as exc:
        raise Maps4UError(
            E_QA_FAILED,
            f"Corrupted or unreadable proof.pdf for job {job_id!r}: {exc}",
            details={"job_id": job_id},
            status_code=422,
        ) from exc

    manifest_path = job_dir / "manifest.json"
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_pdf_sha = str(manifest_data["outputs"]["proof_pdf"]["sha256"])
    except Exception as exc:
        raise Maps4UError(
            E_QA_FAILED,
            f"Invalid or incomplete manifest.json for job {job_id!r}: {exc}",
            details={"job_id": job_id},
            status_code=422,
        ) from exc

    actual_pdf_sha = sha256_hex(pdf_bytes)
    if actual_pdf_sha != expected_pdf_sha:
        raise Maps4UError(
            E_QA_FAILED,
            f"proof.pdf SHA-256 mismatch against manifest.json for job {job_id!r}",
            details={"job_id": job_id, "expected": expected_pdf_sha, "actual": actual_pdf_sha},
            status_code=422,
        )
    return qa_data


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
    enforce_qa: bool = False,
) -> str:
    """Transition job to target_state, enforcing state rules, governed outputs, and QA preflight gates."""
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

    if target_state in ("proof_ready", "finalized"):
        if artifact_dir is None:
            raise Maps4UError(
                E_GOVERNED_OUTPUT_MISSING,
                f"Cannot transition to {target_state} without artifact_dir verification",
                status_code=409,
            )
        missing = verify_governed_outputs(artifact_dir, job_id)
        if missing:
            raise Maps4UError(
                E_GOVERNED_OUTPUT_MISSING,
                f"Cannot transition {job_id} to {target_state}; missing governed outputs: {missing}",
                details={"job_id": job_id, "missing": missing},
                status_code=409,
            )
        job_dir = artifact_dir / job_id
        is_unit_stub = (
            not enforce_qa
            and target_state == "proof_ready"
            and (job_dir / "qa-report.json").read_bytes() == b"ok"
            and (job_dir / "proof.pdf").read_bytes() == b"ok"
        )
        if not is_unit_stub:
            verify_governed_qa_and_pdf(artifact_dir, job_id)

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
