# Changelog

All notable changes to the **Maps4U Street Map System** (`maps4u-maps`) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-mvp] - 2026-10-22 (Stage 6 — Gate G6)

### Added
- **Multi-Stage Production Docker Packaging (`S6.T1`):** Added `Dockerfile` (`python:3.13-slim` builder + runtime stages with `HEALTHCHECK`), `docker-compose.yml` (`api`, `worker`, `redis`, `maps4u_data` volume), and `.dockerignore`.
- **Online SQLite WAL Backup & Restore Drill (`S6.T2`):** Added `scripts/backup_restore_drill.py` using `sqlite3.Connection.backup()` paired with governed bundle archive restoration and SHA-256 verification.
- **Full Operator UAT & Handover Suite (`S6.T3`):** Added `tests/integration/test_stage6_packaging_and_handover.py` and the 3-page PDF comprehensive testing record (`docs/Maps4U_Comprehensive_Testing_Record_v1.0.0-mvp.pdf`).
- **World-Class Repository Documentation & Governance:** Expanded `README.md`, beginner step-by-step guide (`docs/getting-started-beginners.md`), API reference, architecture guide, operator runbook, ADRs (`0001..0009`), GitHub Actions CI, issue/PR templates, and a special dedication to **Winston the Cat**.

---

## [0.5.0-stage5] - 2026-10-22 (Stage 5 — Gate G5)

### Added
- **11-Stage Governed Pipeline Executor (`S5.T1`):** Implemented `src/maps4u/worker/executor.py` orchestrating `created` → `validating` → `queued` → `assessing` → `acquiring` → `transforming` → `styling` → `labelling` → `composing` → `rendering` → `verifying` → `proof_ready`.
- **Cryptographic Review Locking & Corrections (`S5.T1`):** Added `POST /api/jobs/{job_id}/approve` (locking `proof_sha256` in `review_decisions`), `POST /api/jobs/{job_id}/reject` (enforcing mandatory non-blank comment), and `POST /api/jobs/{job_id}/corrections` (spawning immutable child jobs).
- **Deterministic Reproducibility Verifier (`S5.T2`):** Implemented `reproduce(job_id)` in `src/maps4u/bundle/archive.py`.
- **Multi-Pilot Acceptance Verification (`S5.T3`):** Verified 0 blockers, 0 overlaps, and 100% SHA-256 reproducibility across **Maroochydore (`A4-landscape`)**, **Noosa (`A3-landscape`)**, and **Bribie Island (`A4-portrait`)**.

---

## [0.4.0-stage4] - 2026-10-22 (Stage 4 — Gate G4)

### Added
- **Collision-Free `STRtree` Label Engine (`S4.T1`):** Implemented `src/maps4u/labels/engine.py` with priority ordering (`suburb` → `landmark` → `arterial` → `collector` → `local` → `service`), upright angle normalization (`[-90°, +90°)`), and arterial repeat spacing.
- **Map Furniture Composer (`S4.T2`):** Implemented `src/maps4u/layout/furniture.py` generating alphanumeric grid (`A1..H6`), multi-column street index, graphic scale bar, north arrow, legend, title block, and mandatory `© OpenStreetMap contributors (ODbL)` attribution.
- **7-Gate QA Preflight Engine (`S4.T3`):** Implemented `src/maps4u/qa/preflight.py` emitting `qa-report.json` and `qa-report.md`.
- **Cryptographic Provenance Manifest (`S4.T4`):** Implemented `manifest.json` generation linking input hashes to `pdf_sha256` and `content_hash`.

---

## [0.3.0-stage3] - 2026-10-22 (Stage 3 — Gate G3)

### Added
- **Deterministic Vector PDF & Thumbnail Renderer (`S3.T1`):** Implemented `CairoCanvas` (`src/maps4u/render/cairo_canvas.py`) emitting PDF 1.4 vector streams (`proof.pdf`), canonical `drawlog.json`, and raster `thumb.png`.
- **Declarative YAML Style Engine (`S3.T2`):** Implemented `src/maps4u/render/style_engine.py` and `styles/mcy/v1/style.yaml` validated against `schemas/style.schema.json`.
- **Proof Renderer Orchestrator (`S3.T3`):** Implemented `src/maps4u/render/proof_renderer.py` and PDF structural verifier.

---

## [0.2.0-stage2] - 2026-10-21 (Stage 2 — Gate G2)

### Added
- **6 Paper Templates (`S2.T1`):** Added `config/paper_templates.yaml` (`A3`, `A4`, `A5` in `landscape` and `portrait` with `3.0 mm` bleed).
- **Print Scale & Font Legibility Assessor (`S2.T2`):** Implemented `src/maps4u/render/assess.py` and `POST /api/viability` enforcing the non-overridable `1.5 mm` minimum printed font height floor.
- **Static Leaflet Operator Console (`S2.T3`):** Added `src/maps4u/ui/static/index.html` with polygon drawing, preset loading, and live viability checks.

---

## [0.1.0-phase0] - 2026-10-21 (Phase 0 / Stage 1 — Gate G1)

### Added
- **Core Scaffold & SQLite WAL State Machine (`S1.T1`):** Initialized FastAPI + Celery project, SQLite WAL migrations (`0001_initial.sql`), governed state machine, and JSONL audit logging.
- **OSM Overpass Acquisition & 8-Layer GeoPackage Cache (`S1.T2`–`S1.T3`):** Implemented rate-limited Overpass QL fetcher and SHA-256 `.gpkg` snapshot caching.
- **Non-Destructive YAML Client Corrections (`S1.T4`):** Implemented `apply_corrections()` supporting `rename`, `reclass`, `add`, and `remove`.
