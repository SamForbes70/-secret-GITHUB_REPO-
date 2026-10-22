"""System health, readiness, and metadata endpoints (§7.1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from maps4u import __version__
from maps4u.api.deps import get_settings
from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.schemas import MetaResponse

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
    return MetaResponse(
        version=__version__,
        style_refs=[settings.maps4u_default_style],
        papers=["A3", "A4", "A5"],
        orientations=["landscape", "portrait"],
        thresholds={"min_font_mm": settings.maps4u_min_font_mm},
    )
