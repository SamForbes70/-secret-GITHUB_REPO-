# Maps4U Owner Decision Register (`v1.0.0-mvp`)

**System version:** `1.0.0` (`v1.0.0-mvp` — Stages 1–6 Complete)
**Last updated:** 2026-10-23

| ID | Decision Item | Implemented Position (`v1.0.0-mvp`) | Owner | Status | Gate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OD-1 / Q-1** | MCY reference PDF & style baseline | Implemented `styles/mcy/v1/style.yaml` derived from Maroochydore (`MCY`) reference sheet; schema-validated with zero hardcoded styling in Python. | David / Sam | **Implemented & Verified** | Gate G3 |
| **OD-2 / Q-2** | Pilot validation areas (3–5) | Verified end-to-end across **Maroochydore (`A4-landscape`)**, **Noosa (`A3-landscape`)**, and **Bribie Island / Sandstone Point (`A4-portrait`)** with 0 blockers and 0 overlaps. | David | **Implemented & Verified** | Gate G5 |
| **OD-3 / Q-3** | Geofence input mode | Vendored static Leaflet operator web console (`GET /`) + canonical GeoJSON REST API (`POST /api/projects/{id}/geofence`). | Sam | **Approved & Implemented** | Gate G2 |
| **OD-4 / Q-4** | Minimum printed font size | Hard non-overridable `1.5 mm` minimum printed cap height enforced in both `POST /api/viability` and `run_qa()`. | David | **Approved & Implemented** | Gate G2 / G4 |
| **OD-5 / Q-5** | Print colour standard & bleed | Deterministic PDF 1.4 vector streams (`CairoCanvas`) with `3.0 mm` bleed, exact `MediaBox`/`TrimBox`/`BleedBox`, and CMYK-safe hex palette. | David / Printer | **Implemented & Verified** | Gate G3 / G6 |
| **OD-6 / Q-6** | Deployment & hosting target | Multi-stage `Dockerfile` + `docker-compose.yml` (`api`, `worker`, `redis`, `/var/maps4u` volume) for local/appliance pilot; cloud Stage 7 gated. | David | **Approved & Implemented** | Gate G6 |
| **OD-7 / Q-7** | Inset / reverse-side priority | Controlled via `MAPS4U_INSETS_ENABLED` setting; multi-column street index composed automatically. | David | **Implemented** | Gate G4 |
| **OD-8** | Source extract & proof retention | All `.gpkg` snapshots, raw Overpass JSON, and governed 5-artifact bundles retained and verified via `scripts/backup_restore_drill.py`. | David | **Implemented & Verified** | Gate G6 |
| **OD-9** | Identity / OIDC provider | Local mode auth-free with optional `MAPS4U_OPERATOR_TOKEN`; OIDC deferred to Stage 7 cloud profile. | David | **Deferred to Stage 7** | Stage 7 |
