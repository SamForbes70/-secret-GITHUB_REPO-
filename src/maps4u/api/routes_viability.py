"""Viability and paper template endpoints (/api/viability, /api/templates)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from maps4u.api.deps import get_settings
from maps4u.core.config import Settings
from maps4u.core.logging import append_audit_jsonl
from maps4u.core.schemas import ViabilityRequest, ViabilityResponse
from maps4u.geo.crs import validate_and_canonicalise_geofence
from maps4u.layout.templates import get_template, load_paper_templates, template_to_dict
from maps4u.render.assess import StyleSpec, assess

router = APIRouter(prefix="/api", tags=["viability"])


@router.get("/templates")
def list_templates() -> dict[str, dict[str, Any]]:
    templates = load_paper_templates()
    return {k: template_to_dict(tpl) for k, tpl in templates.items()}


@router.post("/viability", response_model=ViabilityResponse)
def check_viability(
    req: ViabilityRequest,
    settings: Settings = Depends(get_settings),
) -> ViabilityResponse:
    geom, _, rev_id = validate_and_canonicalise_geofence(req.geofence)
    template = get_template(req.paper, req.orientation)
    style_spec = StyleSpec(
        style_ref=req.style_ref or settings.maps4u_default_style,
        min_font_mm=settings.maps4u_min_font_mm,
    )
    result = assess(
        geom,
        template,
        style_spec,
        named_feature_count=req.named_feature_count,
        min_font_override_mm=req.min_font_override_mm,
    )
    append_audit_jsonl(
        settings.maps4u_data_dir,
        {
            "event": "viability_assessed",
            "revision_id": rev_id,
            "paper": req.paper,
            "orientation": req.orientation,
            "viable": result.viable,
            "scale_denominator": result.scale_denominator,
        },
    )
    return ViabilityResponse(**result.to_dict())
