"""Projects and immutable geofence revisions endpoints (§6.2 & §7.1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status

from maps4u.api.deps import get_settings
from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, Maps4UError
from maps4u.core.ids import make_project_id
from maps4u.core.logging import append_audit_jsonl
from maps4u.core.schemas import (
    GeofenceRevisionCreateRequest,
    GeofenceRevisionResponse,
    ProjectCreateRequest,
    ProjectResponse,
)
from maps4u.geo.crs import validate_and_canonicalise_geofence

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    req: ProjectCreateRequest,
    settings: Settings = Depends(get_settings),
) -> ProjectResponse:
    now = datetime.now(UTC).isoformat()
    project_id = make_project_id(req.area_name, now)
    with db_session(settings.db_path) as conn:
        conn.execute(
            "INSERT INTO map_projects (project_id, area_name, created_at, reference, notes) VALUES (?, ?, ?, ?, ?)",
            (project_id, req.area_name, now, req.reference, req.notes),
        )
    append_audit_jsonl(
        settings.maps4u_data_dir,
        {"event": "project_created", "project_id": project_id, "area_name": req.area_name},
    )
    return ProjectResponse(
        project_id=project_id,
        area_name=req.area_name,
        created_at=now,
        reference=req.reference,
        notes=req.notes,
    )


@router.get("", response_model=list[ProjectResponse])
def list_projects(settings: Settings = Depends(get_settings)) -> list[ProjectResponse]:
    with db_session(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM map_projects ORDER BY created_at DESC").fetchall()
    return [
        ProjectResponse(
            project_id=str(r["project_id"]),
            area_name=str(r["area_name"]),
            created_at=str(r["created_at"]),
            reference=r["reference"],
            notes=r["notes"],
        )
        for r in rows
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> ProjectResponse:
    with db_session(settings.db_path) as conn:
        proj = conn.execute(
            "SELECT * FROM map_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if proj is None:
            raise Maps4UError(E_NOT_FOUND, f"Project {project_id!r} not found", status_code=404)

        rev = conn.execute(
            "SELECT * FROM geofence_revisions WHERE project_id = ? AND is_current = 1",
            (project_id,),
        ).fetchone()
        jobs = conn.execute(
            "SELECT job_id, status, paper, orientation, created_at FROM jobs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()

    curr_geo: dict[str, Any] | None = None
    if rev is not None:
        curr_geo = {
            "revision_id": str(rev["revision_id"]),
            "geometry": json.loads(str(rev["geometry_json"])),
            "created_at": str(rev["created_at"]),
            "created_by": rev["created_by"],
        }

    return ProjectResponse(
        project_id=str(proj["project_id"]),
        area_name=str(proj["area_name"]),
        created_at=str(proj["created_at"]),
        reference=proj["reference"],
        notes=proj["notes"],
        current_geofence=curr_geo,
        jobs=[dict(j) for j in jobs],
    )


@router.post(
    "/{project_id}/geofence",
    response_model=GeofenceRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_geofence_revision(
    project_id: str,
    req: GeofenceRevisionCreateRequest,
    settings: Settings = Depends(get_settings),
) -> GeofenceRevisionResponse:
    _, canon_json, revision_id = validate_and_canonicalise_geofence(
        {"type": req.type, "coordinates": req.coordinates}
    )
    now = datetime.now(UTC).isoformat()
    with db_session(settings.db_path) as conn:
        proj = conn.execute(
            "SELECT project_id FROM map_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if proj is None:
            raise Maps4UError(E_NOT_FOUND, f"Project {project_id!r} not found", status_code=404)

        conn.execute(
            "UPDATE geofence_revisions SET is_current = 0 WHERE project_id = ?",
            (project_id,),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO geofence_revisions (
                revision_id, project_id, geometry_json, created_at, created_by, is_current
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (revision_id, project_id, canon_json, now, req.created_by),
        )
    append_audit_jsonl(
        settings.maps4u_data_dir,
        {"event": "geofence_revision_saved", "project_id": project_id, "revision_id": revision_id},
    )
    return GeofenceRevisionResponse(
        revision_id=revision_id,
        project_id=project_id,
        is_current=True,
        created_at=now,
    )
