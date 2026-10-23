"""Style version listing endpoint (/api/styles)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from maps4u.api.deps import AuthPrincipal, get_settings, require_authenticated
from maps4u.core.config import Settings, resolve_resource_path
from maps4u.render.style_engine import list_available_styles

router = APIRouter(prefix="/api/styles", tags=["styles"])


@router.get("")
def list_styles(
    settings: Settings = Depends(get_settings),
    _principal: AuthPrincipal = Depends(require_authenticated),
) -> list[dict[str, object]]:
    schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    styles = list_available_styles(style_dir=settings.maps4u_style_dir, schema_path=schema_path)
    return [
        {
            "style_ref": s.style_ref,
            "style_version": s.style_version,
            "approved": s.approved,
            "derived_from": s.derived_from,
            "sha256": s.sha256,
            "scale_bands": [b.name for b in s.scale_bands],
        }
        for s in styles
    ]
