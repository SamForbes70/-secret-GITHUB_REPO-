"""Job creation (with frozen RenderSpecification) and status routes (§7.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from maps4u.api.deps import get_settings
from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, Maps4UError
from maps4u.core.ids import canonical_json_bytes, make_job_id, make_spec_id
from maps4u.core.logging import append_audit_jsonl
from maps4u.core.schemas import JobCreateRequest, JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise Maps4UError(E_NOT_FOUND, f"Job {job_id!r} not found", status_code=404)
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
