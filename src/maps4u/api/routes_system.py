"""System health, readiness, and metadata endpoints (§7.1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from maps4u import __version__
from maps4u.api.deps import get_settings
from maps4u.core.config import Settings, resolve_resource_path
from maps4u.core.db import db_session
from maps4u.core.schemas import MetaResponse
from maps4u.render.style_engine import list_available_styles

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    with db_session(settings.db_path) as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ready": True, "queue_mode": settings.maps4u_queue}


@router.get("/api/meta", response_model=MetaResponse)
def get_meta(settings: Settings = Depends(get_settings)) -> MetaResponse:
    schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    styles = list_available_styles(style_dir=settings.maps4u_style_dir, schema_path=schema_path)
    style_refs = [s.style_ref for s in styles] or [settings.maps4u_default_style]
    return MetaResponse(
        version=__version__,
        style_refs=style_refs,
        papers=["A3", "A4", "A5"],
        orientations=["landscape", "portrait"],
        thresholds={"min_font_mm": settings.maps4u_min_font_mm},
    )
