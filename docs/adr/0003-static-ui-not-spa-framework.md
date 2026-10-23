# ADR-0003: Vendored Static Leaflet Operator Console

- **Status:** Accepted (Stage 2 Gate `G2`)
- **Date:** 2026-10-21
- **Owners:** MAPS4U Engineering

## Context
Operators require an interactive map preview to draw/edit WGS84 geofences, select paper sizes (`A3`/`A4`/`A5`) and orientations (`landscape`/`portrait`), inspect live scale and font legibility viability, trigger render jobs, and approve/reject proofs without maintaining a complex Node.js SPA build pipeline.

## Decision
Serve a static HTML5 + vanilla JavaScript + Leaflet operator console directly from FastAPI (`src/maps4u/ui/static/index.html`, mounted at `GET /`).

## Verification
- `tests/api/test_stage2_viability_and_ui.py`
- `tests/integration/test_stage6_packaging_and_handover.py` (`test_s6_t3_full_uat_operator_journey`)
