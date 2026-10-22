"""Style version listing endpoint (/api/styles)."""

from __future__ import annotations

from fastapi import APIRouter

from maps4u.render.style_engine import load_style_yaml

router = APIRouter(prefix="/api/styles", tags=["styles"])


@router.get("")
def list_styles() -> list[dict[str, object]]:
    style = load_style_yaml()
    return [
        {
            "style_ref": style.style_ref,
            "style_version": style.style_version,
            "approved": style.approved,
            "derived_from": style.derived_from,
            "sha256": style.sha256,
            "scale_bands": [b.name for b in style.scale_bands],
        }
    ]
