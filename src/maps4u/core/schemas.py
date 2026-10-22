"""Pydantic API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    area_name: str = Field(..., min_length=1, max_length=120)
    reference: str | None = None
    notes: str | None = None


class ProjectResponse(BaseModel):
    project_id: str
    area_name: str
    created_at: str
    reference: str | None = None
    notes: str | None = None
    current_geofence: dict[str, Any] | None = None
    jobs: list[dict[str, Any]] = Field(default_factory=list)


class GeofenceRevisionCreateRequest(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]
    created_by: str | None = "operator"


class GeofenceRevisionResponse(BaseModel):
    revision_id: str
    project_id: str
    is_current: bool
    created_at: str


class JobCreateRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    geofence_revision: str = Field(..., min_length=1)
    paper: Literal["A3", "A4", "A5"]
    orientation: Literal["landscape", "portrait"]
    edition: str = "ed1"
    style_ref: str | None = None
    corrections_ref: str | None = None


class JobResponse(BaseModel):
    job_id: str
    project_id: str | None
    geofence_revision: str | None
    spec_id: str | None
    area_name: str
    paper: str
    orientation: str
    style_ref: str
    status: str
    scale_denominator: float | None = None
    min_font_mm: float | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str
    updated_at: str


class MetaResponse(BaseModel):
    version: str
    style_refs: list[str]
    papers: list[str]
    orientations: list[str]
    thresholds: dict[str, float]
