"""Projects and immutable geofence revisions endpoints (§6.2 & §7.1, hardened for BUG-003, BUG-007)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status

from maps4u.api.deps import AuthPrincipal, get_settings, require_authenticated, require_operator
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
from maps4u.geo.crs import compute_geometry_sha256, validate_and_canonicalise_geofence

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    req: ProjectCreateRequest,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_operator),
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
def list_projects(
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> list[ProjectResponse]:
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
    _principal: AuthPrincipal = Depends(require_authenticated),
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
        geom_str = str(rev["geometry_json"])
        curr_geo = {
            "revision_id": str(rev["revision_id"]),
            "geometry_sha256": compute_geometry_sha256(geom_str),
            "geometry": json.loads(geom_str),
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
    principal: AuthPrincipal = Depends(require_operator),
) -> GeofenceRevisionResponse:
    _, canon_json, revision_id = validate_and_canonicalise_geofence(
        {"type": req.type, "coordinates": req.coordinates},
        project_id=project_id,
    )
    geom_sha = compute_geometry_sha256(canon_json)
    now = datetime.now(UTC).isoformat()
    actor = principal.identity if principal.authenticated else (req.created_by or "operator")

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
        existing = conn.execute(
            "SELECT revision_id, created_at, created_by FROM geofence_revisions WHERE revision_id = ? AND project_id = ?",
            (revision_id, project_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO geofence_revisions (
                    revision_id, project_id, geometry_json, created_at, created_by, is_current
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (revision_id, project_id, canon_json, now, actor),
            )
            created_at = now
            created_by = actor
        else:
            conn.execute(
                "UPDATE geofence_revisions SET is_current = 1 WHERE revision_id = ? AND project_id = ?",
                (revision_id, project_id),
            )
            created_at = str(existing["created_at"])
            created_by = existing["created_by"]

    append_audit_jsonl(
        settings.maps4u_data_dir,
        {
            "event": "geofence_revision_saved",
            "project_id": project_id,
            "revision_id": revision_id,
            "geometry_sha256": geom_sha,
        },
    )
    return GeofenceRevisionResponse(
        revision_id=revision_id,
        geometry_sha256=geom_sha,
        project_id=project_id,
        is_current=True,
        created_at=created_at,
        created_by=created_by,
        geometry=json.loads(canon_json),
    )


@router.get(
    "/{project_id}/revisions",
    response_model=list[GeofenceRevisionResponse],
)
def list_geofence_revisions(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> list[GeofenceRevisionResponse]:
    with db_session(settings.db_path) as conn:
        proj = conn.execute(
            "SELECT project_id FROM map_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if proj is None:
            raise Maps4UError(E_NOT_FOUND, f"Project {project_id!r} not found", status_code=404)

        rows = conn.execute(
            """
            SELECT revision_id, project_id, geometry_json, created_at, created_by, is_current
            FROM geofence_revisions
            WHERE project_id = ?
            ORDER BY created_at DESC
            """,
            (project_id,),
        ).fetchall()

    return [
        GeofenceRevisionResponse(
            revision_id=str(r["revision_id"]),
            geometry_sha256=compute_geometry_sha256(str(r["geometry_json"])),
            project_id=str(r["project_id"]),
            is_current=bool(r["is_current"]),
            created_at=str(r["created_at"]),
            created_by=r["created_by"],
            geometry=json.loads(str(r["geometry_json"])),
        )
        for r in rows
    ]
