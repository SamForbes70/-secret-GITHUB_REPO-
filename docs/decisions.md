# MAPS4U Owner Decision Register

**System version:** 0.1.0 (Phase 0 / Stage 0–1)
**Last updated:** 2026-10-21

| ID | Decision Item | Provisional Position (Active) | Owner | Status | Gate Impact |
|---|---|---|---|---|---|
| OD-1 / Q-1 | MCY reference PDF & reproduction rights | PA-1: Proceed with starter MCY-derived YAML spec; confirm source PDF & rights before Stage 3 sign-off | David / Sam | Indicative ✓ (confirm at Stage 3) | Gates Stage 3 |
| OD-2 / Q-2 | Pilot validation areas (3–5) | PA-2: Maroochydore (MCY), Noosa, Bribie Island, Sandstone Point | David | Open (Provisional active) | Gates Stage 5 |
| OD-3 / Q-3 | Geofence input mode | PA-3: Lightweight web tool (Leaflet + draw) + GeoJSON API | Sam | Approved for Pilot | Stage 2 |
| OD-4 / Q-4 | Minimum printed font size | PA-4: 1.5 mm default (`MAPS4U_MIN_FONT_MM=1.5`), configurable in style YAML | David | Indicative ✓ (confirm via print sample) | Stage 2 / Stage 5 |
| OD-5 / Q-5 | Print colour standard & bleed | PA-5: RGB vector PDF with CMYK-safe palette first; PDF/X Ghostscript export path documented | David / Printer | Indicative ✓ | Stage 6 |
| OD-6 / Q-6 | Deployment & hosting target | PA-6: Local Docker service on operator laptop for pilot; cloud hosting deferred to Stage 7 | David | Approved for Pilot | Stage 6 / Stage 7 |
| OD-7 / Q-7 | Inset / reverse-side priority | PA-7: Behind feature flag `MAPS4U_INSETS_ENABLED=true` | David | Open (Provisional active) | Stage 4 |
| OD-8 | Source extract & rejected proof retention | Retain all snapshots referenced by approved proofs; manual purge only in MVP | David | Open (Provisional active) | Stage 6 |
| OD-9 | Identity / OIDC provider | Local mode auth-free (optional operator token); OIDC deferred to Stage 7 | David | Deferred to Stage 7 | Stage 7 |
