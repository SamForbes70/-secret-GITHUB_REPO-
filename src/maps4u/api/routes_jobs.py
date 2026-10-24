"""Job creation, execution, artifact retrieval, review locking, and corrections routes (v1.0.1 hardened)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from maps4u.api.deps import (
    AuthPrincipal,
    get_settings,
    require_authenticated,
    require_operator,
    require_reviewer,
)
from maps4u.bundle.archive import reproduce
from maps4u.core.config import Settings, resolve_resource_path
from maps4u.core.db import db_session
from maps4u.core.errors import (
    E_CORRECTIONS_INVALID,
    E_NOT_FOUND,
    E_STATE_ILLEGAL,
    E_STORAGE,
    Maps4UError,
)
from maps4u.core.ids import canonical_json_bytes, make_job_id, make_spec_id, sha256_hex
from maps4u.core.logging import append_audit_jsonl
from maps4u.core.schemas import JobCreateRequest, JobResponse
from maps4u.core.state import GOVERNED_OUTPUT_FILES, transition_job_state
from maps4u.geo.corrections import load_and_validate_corrections, resolve_safe_corrections_path
from maps4u.render.style_engine import load_style_by_ref
from maps4u.worker.executor import execute_job_pipeline
from maps4u.worker.tasks import celery_app, run_job_task

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class ReviewDecisionRequest(BaseModel):
    reviewer: str = Field(default="reviewer", min_length=1, max_length=120)
    comment: str | None = None


class RejectDecisionRequest(BaseModel):
    reviewer: str = Field(default="reviewer", min_length=1, max_length=120)
    comment: str = Field(..., min_length=1)


class CorrectionsSubmitRequest(BaseModel):
    yaml_content: str = Field(..., min_length=1)
    author: str = Field(default="operator", min_length=1)


def _row_to_job_response(row: Any) -> JobResponse:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    retry_cnt = int(row["retry_count"] or 0) if "retry_count" in keys else 0
    return JobResponse(
        job_id=str(row["job_id"]),
        project_id=row["project_id"],
        geofence_revision=row["geofence_revision"],
        spec_id=row["spec_id"],
        area_name=str(row["area_name"]),
        paper=str(row["paper"]),
        orientation=str(row["orientation"]),
        style_ref=str(row["style_ref"]),
        status=str(row["status"]),
        scale_denominator=row["scale_denominator"],
        min_font_mm=row["min_font_mm"],
        error_code=row["error_code"],
        error_detail=row["error_detail"],
        retry_count=retry_cnt,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _serialize_settings(settings: Settings) -> dict[str, Any]:
    return {
        "MAPS4U_ENV": settings.maps4u_env,
        "MAPS4U_QUEUE": settings.maps4u_queue,
        "MAPS4U_DATA_DIR": str(settings.maps4u_data_dir),
        "MAPS4U_DB_PATH": str(settings.db_path),
        "MAPS4U_ARTIFACT_DIR": str(settings.artifact_dir),
        "MAPS4U_CACHE_DIR": str(settings.cache_dir),
        "MAPS4U_REDIS_URL": settings.redis_url,
        "MAPS4U_OVERPASS_URL": settings.maps4u_overpass_url,
        "MAPS4U_OVERPASS_TIMEOUT_S": settings.maps4u_overpass_timeout_s,
        "MAPS4U_OVERPASS_MAX_CONCURRENCY": settings.maps4u_overpass_max_concurrency,
        "MAPS4U_CACHE_MAX_AGE_DAYS": settings.maps4u_cache_max_age_days,
        "MAPS4U_DEFAULT_STYLE": settings.maps4u_default_style,
        "MAPS4U_STYLE_DIR": str(settings.maps4u_style_dir),
        "MAPS4U_CONFIG_DIR": str(settings.maps4u_config_dir),
        "MAPS4U_SCHEMA_DIR": str(settings.maps4u_schema_dir),
        "MAPS4U_MIN_FONT_MM": settings.maps4u_min_font_mm,
        "MAPS4U_RENDER_DPI": settings.maps4u_render_dpi,
        "MAPS4U_INSETS_ENABLED": settings.maps4u_insets_enabled,
    }


def _verify_artifact_integrity(job_id: str, artifact_name: str, path: Path, settings: Settings) -> None:
    """Verify artifact SHA-256 against manifest.json and locked review_decisions (BUG-015)."""
    job_dir = settings.artifact_dir / job_id
    actual_bytes = path.read_bytes()
    actual_sha = sha256_hex(actual_bytes)

    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise Maps4UError(
                E_STORAGE,
                f"Manifest integrity error for job {job_id!r}: {exc}",
                details={"job_id": job_id, "artifact": artifact_name},
                status_code=409,
            ) from exc

        manifest_copy = dict(manifest_data)
        recorded_manifest_sha = manifest_copy.pop("manifest_sha256", None)
        if not recorded_manifest_sha or sha256_hex(canonical_json_bytes(manifest_copy)) != recorded_manifest_sha:
            raise Maps4UError(
                E_STORAGE,
                f"Manifest self-hash tampering detected for job {job_id!r}",
                details={"job_id": job_id, "artifact": artifact_name},
                status_code=409,
            )

        key_map = {
            "proof.pdf": "proof_pdf",
            "thumb.png": "thumb_png",
            "qa-report.json": "qa_report_json",
            "qa-report.md": "qa_report_md",
        }
        out_key = key_map.get(artifact_name)
        if out_key:
            expected_sha = str(manifest_data.get("outputs", {}).get(out_key, {}).get("sha256", ""))
            if expected_sha and actual_sha != expected_sha:
                raise Maps4UError(
                    E_STORAGE,
                    f"Artifact integrity check failed for {artifact_name!r} on job {job_id!r}: SHA-256 mismatch",
                    details={
                        "job_id": job_id,
                        "artifact": artifact_name,
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                    },
                    status_code=409,
                )

    if artifact_name == "proof.pdf":
        with db_session(settings.db_path) as conn:
            rev_row = conn.execute(
                "SELECT proof_sha256 FROM review_decisions "
                "WHERE job_id = ? AND decision = 'approved' ORDER BY rowid DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        if rev_row is not None:
            locked_sha = str(rev_row["proof_sha256"])
            if actual_sha != locked_sha:
                raise Maps4UError(
                    E_STORAGE,
                    f"Post-approval modification detected on proof.pdf for finalized job {job_id!r}",
                    details={
                        "job_id": job_id,
                        "locked_proof_sha256": locked_sha,
                        "actual_sha256": actual_sha,
                    },
                    status_code=409,
                )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    req: JobCreateRequest,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_operator),
) -> JobResponse:
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    yyyymm = now.strftime("%Y-%m")
    style_ref = req.style_ref or settings.maps4u_default_style

    # Validate style_ref upfront so invalid styles fail fast (BUG-013)
    style_schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    loaded_style = load_style_by_ref(style_ref, style_dir=settings.maps4u_style_dir, schema_path=style_schema_path)
    style_ref = loaded_style.style_ref

    with db_session(settings.db_path) as conn:
        proj = conn.execute(
            "SELECT * FROM map_projects WHERE project_id = ?", (req.project_id,)
        ).fetchone()
        if proj is None:
            raise Maps4UError(E_NOT_FOUND, f"Project {req.project_id!r} not found", status_code=404)

        rev = conn.execute(
            "SELECT * FROM geofence_revisions WHERE revision_id = ? AND project_id = ?",
            (req.geofence_revision, req.project_id),
        ).fetchone()
        if rev is None:
            raise Maps4UError(
                E_NOT_FOUND,
                f"Geofence revision {req.geofence_revision!r} not found for project {req.project_id!r}",
                status_code=404,
            )

        if req.corrections_ref is not None:
            resolve_safe_corrections_path(
                req.corrections_ref,
                data_dir=settings.maps4u_data_dir,
                artifact_dir=settings.artifact_dir,
                conn=conn,
            )

        spec_payload = {
            "project_id": req.project_id,
            "geofence_revision": req.geofence_revision,
            "paper": req.paper,
            "orientation": req.orientation,
            "edition": req.edition,
            "style_ref": style_ref,
            "corrections_ref": req.corrections_ref,
            "seed": 0,
        }
        spec_id = make_spec_id(spec_payload)
        spec_json = canonical_json_bytes(spec_payload).decode("utf-8")
        job_id = make_job_id(str(proj["area_name"]), yyyymm, req.edition, suffix=spec_id[:6])

        existing_job = conn.execute(
            "SELECT job_id, status FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if existing_job is not None:
            raise Maps4UError(
                E_STATE_ILLEGAL,
                (
                    f"Job {job_id!r} already exists in state {existing_job['status']!r}; "
                    "duplicate submission rejected (use /reproduce or a new edition)"
                ),
                details={
                    "job_id": job_id,
                    "status": str(existing_job["status"]),
                    "spec_id": spec_id,
                },
                status_code=409,
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO render_specifications (
                spec_id, project_id, geofence_revision, paper, orientation,
                style_ref, corrections_id, spec_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec_id,
                req.project_id,
                req.geofence_revision,
                req.paper,
                req.orientation,
                style_ref,
                req.corrections_ref,
                spec_json,
                now_iso,
            ),
        )

        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, project_id, geofence_revision, spec_id, area_name,
                    geofence_geojson, paper, orientation, edition, style_ref,
                    corrections_ref, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'created', ?, ?)
                """,
                (
                    job_id,
                    req.project_id,
                    req.geofence_revision,
                    spec_id,
                    str(proj["area_name"]),
                    str(rev["geometry_json"]),
                    req.paper,
                    req.orientation,
                    req.edition,
                    style_ref,
                    req.corrections_ref,
                    now_iso,
                    now_iso,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise Maps4UError(
                E_STATE_ILLEGAL,
                f"Job {job_id!r} already exists (concurrent duplicate submission rejected)",
                details={"job_id": job_id, "spec_id": spec_id},
                status_code=409,
            ) from exc
        conn.execute(
            "INSERT INTO job_events (job_id, ts, stage, event, payload_json) VALUES (?, ?, 'created', 'job_created', ?)",
            (job_id, now_iso, spec_json),
        )

    append_audit_jsonl(
        settings.maps4u_data_dir,
        {"event": "job_created", "job_id": job_id, "spec_id": spec_id},
    )
    return JobResponse(
        job_id=job_id,
        project_id=req.project_id,
        geofence_revision=req.geofence_revision,
        spec_id=spec_id,
        area_name=str(proj["area_name"]),
        paper=req.paper,
        orientation=req.orientation,
        style_ref=style_ref,
        status="created",
        created_at=now_iso,
        updated_at=now_iso,
    )


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status_filter: str | None = None,
    limit: int = 50,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> list[JobResponse]:
    with db_session(settings.db_path) as conn:
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status_filter, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_job_response(r) for r in rows]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> JobResponse:
    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
    return _row_to_job_response(row)


@router.post("/{job_id}/run", response_model=JobResponse)
def run_job_endpoint(
    job_id: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_operator),
) -> JobResponse:
    if settings.maps4u_queue == "celery":
        with db_session(settings.db_path) as conn:
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
            current_status = str(row["status"])
            if current_status not in ("created", "failed"):
                raise Maps4UError(
                    E_STATE_ILLEGAL,
                    f"Job {job_id!r} in state {current_status!r} is already queued or active (duplicate dispatch blocked)",
                    details={"job_id": job_id, "status": current_status},
                    status_code=409,
                )
            if current_status == "created":
                transition_job_state(
                    conn,
                    job_id=job_id,
                    target_state="validating",
                    stage="validating",
                    event="stage_validating_started",
                    data_dir=settings.maps4u_data_dir,
                    artifact_dir=settings.artifact_dir,
                )
                transition_job_state(
                    conn,
                    job_id=job_id,
                    target_state="queued",
                    stage="queued",
                    event="job_dispatched_celery",
                    data_dir=settings.maps4u_data_dir,
                    artifact_dir=settings.artifact_dir,
                )
            elif current_status == "failed":
                conn.execute(
                    "UPDATE jobs SET retry_count = COALESCE(retry_count, 0) + 1 WHERE job_id = ?",
                    (job_id,),
                )
                transition_job_state(
                    conn,
                    job_id=job_id,
                    target_state="queued",
                    stage="queued",
                    event="job_retried_celery",
                    data_dir=settings.maps4u_data_dir,
                    artifact_dir=settings.artifact_dir,
                )
        celery_app.conf.broker_url = settings.redis_url
        celery_app.conf.result_backend = settings.redis_url
        run_job_task.apply_async(
            args=[job_id],
            kwargs={"settings_overrides": _serialize_settings(settings)},
        )
        return get_job(job_id, settings)

    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
        current_status = str(row["status"])
        if current_status not in ("created", "queued", "failed"):
            raise Maps4UError(
                E_STATE_ILLEGAL,
                f"Job {job_id!r} in state {current_status!r} cannot be dispatched for execution",
                details={"job_id": job_id, "status": current_status},
                status_code=409,
            )

    execute_job_pipeline(job_id, settings)
    return get_job(job_id, settings)


@router.post("/{job_id}/reproduce")
def reproduce_job_endpoint(
    job_id: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_operator),
) -> dict[str, Any]:
    repro_dir = settings.artifact_dir / job_id / "reproduce"
    result = reproduce(job_id, settings, repro_dir)
    append_audit_jsonl(
        settings.maps4u_data_dir,
        {"event": "job_reproduced", "job_id": job_id, "matched": result["matched"]},
    )
    return result


@router.get("/{job_id}/artifacts/{artifact_name}")
def get_job_artifact(
    job_id: str,
    artifact_name: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> FileResponse:
    if artifact_name not in GOVERNED_OUTPUT_FILES:
        raise Maps4UError(
            E_NOT_FOUND,
            f"Unknown governed artifact {artifact_name!r}",
            status_code=404,
        )
    path = settings.artifact_dir / job_id / artifact_name
    if not path.is_file():
        raise Maps4UError(
            E_NOT_FOUND,
            f"Artifact {artifact_name!r} for job {job_id!r} not found",
            status_code=404,
        )
    _verify_artifact_integrity(job_id, artifact_name, path, settings)
    media_types = {
        "proof.pdf": "application/pdf",
        "thumb.png": "image/png",
        "qa-report.md": "text/markdown",
        "qa-report.json": "application/json",
        "manifest.json": "application/json",
    }
    return FileResponse(path, media_type=media_types.get(artifact_name, "application/octet-stream"))


@router.post("/{job_id}/approve")
def approve_job(
    job_id: str,
    req: ReviewDecisionRequest,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(require_reviewer),
) -> dict[str, Any]:
    pdf_path = settings.artifact_dir / job_id / "proof.pdf"
    if not pdf_path.is_file():
        raise Maps4UError(E_NOT_FOUND, f"Proof PDF for job {job_id!r} not found", status_code=404)
    proof_sha256 = sha256_hex(pdf_path.read_bytes())
    now_iso = datetime.now(UTC).isoformat()
    effective_reviewer = principal.identity if principal.authenticated else req.reviewer

    with db_session(settings.db_path) as conn:
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="finalized",
            stage="review",
            event="job_approved",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
            payload={
                "reviewer": effective_reviewer,
                "authenticated_role": principal.role,
                "proof_sha256": proof_sha256,
                "comment": req.comment,
            },
        )
        conn.execute(
            """
            INSERT INTO review_decisions (job_id, reviewer, decision, comment, proof_sha256, decided_at)
            VALUES (?, ?, 'approved', ?, ?, ?)
            """,
            (job_id, effective_reviewer, req.comment, proof_sha256, now_iso),
        )

    return {
        "job_id": job_id,
        "status": "finalized",
        "decision": "approved",
        "reviewer": effective_reviewer,
        "proof_sha256": proof_sha256,
        "decided_at": now_iso,
    }


@router.post("/{job_id}/reject")
def reject_job(
    job_id: str,
    req: RejectDecisionRequest,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(require_reviewer),
) -> dict[str, Any]:
    comment_clean = req.comment.strip()
    if not comment_clean:
        raise Maps4UError(
            E_CORRECTIONS_INVALID,
            "Rejection comment is required and cannot be blank.",
            status_code=422,
        )
    pdf_path = settings.artifact_dir / job_id / "proof.pdf"
    proof_sha256 = sha256_hex(pdf_path.read_bytes()) if pdf_path.is_file() else ("0" * 64)
    now_iso = datetime.now(UTC).isoformat()
    effective_reviewer = principal.identity if principal.authenticated else req.reviewer

    with db_session(settings.db_path) as conn:
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="rejected",
            stage="review",
            event="job_rejected",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
            payload={
                "reviewer": effective_reviewer,
                "authenticated_role": principal.role,
                "comment": comment_clean,
                "proof_sha256": proof_sha256,
            },
        )
        conn.execute(
            """
            INSERT INTO review_decisions (job_id, reviewer, decision, comment, proof_sha256, decided_at)
            VALUES (?, ?, 'rejected', ?, ?, ?)
            """,
            (job_id, effective_reviewer, comment_clean, proof_sha256, now_iso),
        )

    return {
        "job_id": job_id,
        "status": "rejected",
        "decision": "rejected",
        "reviewer": effective_reviewer,
        "comment": comment_clean,
        "proof_sha256": proof_sha256,
        "decided_at": now_iso,
    }


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_operator),
) -> JobResponse:
    with db_session(settings.db_path) as conn:
        row = conn.execute(
            "SELECT status, error_code, error_detail, COALESCE(retry_count, 0) AS retry_count FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
        new_retry_count = int(row["retry_count"] or 0) + 1
        prev_error_code = row["error_code"]
        prev_error_detail = row["error_detail"]
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="queued",
            stage="queued",
            event="job_retried",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
            payload={
                "retry_count": new_retry_count,
                "previous_error_code": prev_error_code,
                "previous_error_detail": prev_error_detail,
                "queue_mode": settings.maps4u_queue,
            },
        )
        conn.execute(
            "UPDATE jobs SET retry_count = ?, error_code = NULL, error_detail = NULL WHERE job_id = ?",
            (new_retry_count, job_id),
        )

    if settings.maps4u_queue == "celery":
        celery_app.conf.broker_url = settings.redis_url
        celery_app.conf.result_backend = settings.redis_url
        run_job_task.apply_async(
            args=[job_id],
            kwargs={"settings_overrides": _serialize_settings(settings)},
        )
        return get_job(job_id, settings)

    execute_job_pipeline(job_id, settings)
    return get_job(job_id, settings)


@router.post("/{job_id}/corrections", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def submit_job_corrections(
    job_id: str,
    req: CorrectionsSubmitRequest,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(require_operator),
) -> JobResponse:
    with db_session(settings.db_path) as conn:
        parent = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if parent is None:
        raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)

    corr_dir = settings.maps4u_data_dir / "corrections"
    corr_dir.mkdir(parents=True, exist_ok=True)
    corr_bytes = req.yaml_content.encode("utf-8")
    corr_sha = sha256_hex(corr_bytes)
    corr_id = f"corr-{corr_sha[:12]}"
    corr_path = corr_dir / f"{corr_id}.yaml"
    corr_path.write_bytes(corr_bytes)

    schema_path = resolve_resource_path("schemas/corrections.schema.json", explicit_base=settings.maps4u_schema_dir)
    load_and_validate_corrections(corr_path, schema_path=schema_path)

    now_iso = datetime.now(UTC).isoformat()
    with db_session(settings.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO corrections_files (corrections_id, path, applied_at, sha256) VALUES (?, ?, ?, ?)",
            (corr_id, str(corr_path), now_iso, corr_sha),
        )

    new_req = JobCreateRequest(
        project_id=str(parent["project_id"]),
        geofence_revision=str(parent["geofence_revision"]),
        paper=str(parent["paper"]),  # type: ignore[arg-type]
        orientation=str(parent["orientation"]),  # type: ignore[arg-type]
        edition=f"{parent['edition'] or 'ed1'}-{corr_id[:8]}",
        style_ref=str(parent["style_ref"]),
        corrections_ref=str(corr_path),
    )
    return create_job(new_req, settings, principal)
