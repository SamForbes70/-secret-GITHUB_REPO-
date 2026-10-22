"""Job creation, execution, artifact retrieval, approve/reject review locking, and corrections routes (§7.1, Stage 5 S5.T1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from maps4u.api.deps import get_settings
from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_CORRECTIONS_INVALID, E_NOT_FOUND, Maps4UError
from maps4u.core.ids import canonical_json_bytes, make_job_id, make_spec_id, sha256_hex
from maps4u.core.logging import append_audit_jsonl
from maps4u.core.schemas import JobCreateRequest, JobResponse
from maps4u.core.state import GOVERNED_OUTPUT_FILES, transition_job_state
from maps4u.geo.corrections import load_and_validate_corrections
from maps4u.worker.executor import execute_job_pipeline

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class ReviewDecisionRequest(BaseModel):
    reviewer: str = Field(..., min_length=1, max_length=120)
    comment: str | None = None


class RejectDecisionRequest(BaseModel):
    reviewer: str = Field(..., min_length=1, max_length=120)
    comment: str = Field(..., min_length=1)


class CorrectionsSubmitRequest(BaseModel):
    yaml_content: str = Field(..., min_length=1)
    author: str = Field(default="operator", min_length=1)


def _row_to_job_response(row: Any) -> JobResponse:
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
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    req: JobCreateRequest,
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    yyyymm = now.strftime("%Y-%m")
    style_ref = req.style_ref or settings.maps4u_default_style

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

        job_id = make_job_id(str(proj["area_name"]), yyyymm, req.edition, suffix=spec_id[:6])
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs (
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
) -> JobResponse:
    execute_job_pipeline(job_id, settings)
    return get_job(job_id, settings)


@router.get("/{job_id}/artifacts/{artifact_name}")
def get_job_artifact(
    job_id: str,
    artifact_name: str,
    settings: Settings = Depends(get_settings),
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
) -> dict[str, Any]:
    pdf_path = settings.artifact_dir / job_id / "proof.pdf"
    if not pdf_path.is_file():
        raise Maps4UError(E_NOT_FOUND, f"Proof PDF for job {job_id!r} not found", status_code=404)
    proof_sha256 = sha256_hex(pdf_path.read_bytes())
    now_iso = datetime.now(UTC).isoformat()

    with db_session(settings.db_path) as conn:
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="finalized",
            stage="review",
            event="job_approved",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
            payload={"reviewer": req.reviewer, "proof_sha256": proof_sha256, "comment": req.comment},
        )
        conn.execute(
            """
            INSERT INTO review_decisions (job_id, reviewer, decision, comment, proof_sha256, decided_at)
            VALUES (?, ?, 'approved', ?, ?, ?)
            """,
            (job_id, req.reviewer, req.comment, proof_sha256, now_iso),
        )

    return {
        "job_id": job_id,
        "status": "finalized",
        "decision": "approved",
        "reviewer": req.reviewer,
        "proof_sha256": proof_sha256,
        "decided_at": now_iso,
    }


@router.post("/{job_id}/reject")
def reject_job(
    job_id: str,
    req: RejectDecisionRequest,
    settings: Settings = Depends(get_settings),
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

    with db_session(settings.db_path) as conn:
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="rejected",
            stage="review",
            event="job_rejected",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
            payload={"reviewer": req.reviewer, "comment": comment_clean, "proof_sha256": proof_sha256},
        )
        conn.execute(
            """
            INSERT INTO review_decisions (job_id, reviewer, decision, comment, proof_sha256, decided_at)
            VALUES (?, ?, 'rejected', ?, ?, ?)
            """,
            (job_id, req.reviewer, comment_clean, proof_sha256, now_iso),
        )

    return {
        "job_id": job_id,
        "status": "rejected",
        "decision": "rejected",
        "reviewer": req.reviewer,
        "comment": comment_clean,
        "proof_sha256": proof_sha256,
        "decided_at": now_iso,
    }


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    with db_session(settings.db_path) as conn:
        transition_job_state(
            conn,
            job_id=job_id,
            target_state="queued",
            stage="queued",
            event="job_retried",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
        )
    return get_job(job_id, settings)


@router.post("/{job_id}/corrections", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def submit_job_corrections(
    job_id: str,
    req: CorrectionsSubmitRequest,
    settings: Settings = Depends(get_settings),
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

    # Validate against corrections schema before accepting
    load_and_validate_corrections(corr_path)

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
    return create_job(new_req, settings)
