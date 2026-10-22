"""Style version listing endpoint (/api/styles)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from maps4u.api.deps import get_settings
from maps4u.core.config import Settings

router = APIRouter(prefix="/api/styles", tags=["styles"])


@router.get("")
def list_styles(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return [{"style_ref": settings.maps4u_default_style, "approved": False}]
