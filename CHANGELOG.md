# Changelog

All notable changes to the **Maps4U Street Map System** (`maps4u-maps`) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.4] - 2026-10-25 — On-Demand Custom Map CLI, MCY Style Sign-Off (`OD-1`) & 5-Area Live Showcase

### Added
- **On-Demand Custom Map Generator CLI (`scripts/generate_custom_map.py`):** Generates, approves (`finalized`), verifies (`reproduce()`), and exports print-ready vector PDF street maps (`proof.pdf`), previews (`thumb.png`), QA reports (`qa-report.md`), and provenance manifests (`manifest.json`) for any town, suburb (via preset or OpenStreetMap Nominatim geocoding), or explicit `--bbox` across `A3`/`A4`/`A5` (`landscape`/`portrait`).
- **Live Custom Map Showcase (`docs/assets/pilots/`):** Added live OpenStreetMap proofs and previews for **Mooloolaba (`A4-landscape`, `1:12,500`)** and **Caloundra (`A3-landscape`, `1:7,500`)** alongside Maroochydore, Noosa Heads, and Bribie Island — Sandstone Point.
- **GitHub Actions Activation Helper (`scripts/activate_github_actions.sh`):** One-command helper to copy `deploy/github-actions-ci.yml` to `.github/workflows/ci.yml` once authenticated with `workflow` scope (`CI-001`).
- **Owner & Press Sign-Off (`OD-1`, `OD-2`, `OD-8`):** Marked `styles/mcy/v1/style.yaml` (`approved: true`) and updated `docs/decisions.md`.
- **Automated Regression Suite (`98/98 passing`):** Added `test_generate_custom_map_cli_on_demand_and_style_signoff`.

## [1.0.3] — 2026-10-25 (Cartographic Polish & Live Overpass 3-Pilot Verification)

### Added
- **Same-Name Street Label Spacing (`min_same_name_distance_mm`):** Added configurable minimum spacing (`52.0 mm` default in `styles/mcy/v1/style.yaml` and `schemas/style.schema.json`) and longest-segment-first sorting in `src/maps4u/labels/engine.py` so multi-segment OSM roads (`Horton Parade`, `Bribie Island Road`, `Noosa Drive`) repeat at clean, well-spaced intervals across the sheet instead of clustering on adjacent short segments.
- **Visual Legend Swatches (`src/maps4u/layout/furniture.py`):** Rendered colour-accurate polygon fills (`water`, `parks`), double-cased arterial road swatches (`roads`), and stroke swatches (`coastline`, `water_lines`, `boundaries`) inside the Legend box.
- **Rendered Multi-Column Street Index Panel (`src/maps4u/layout/furniture.py`):** Added a bordered multi-column `STREET INDEX` panel (`Street Name [Grid Cell]`) in the reserved furniture sidebar below the Legend on landscape sheets and below the Title Block on portrait sheets.
- **Live Overpass 3-Area Pilot Runner (`scripts/run_live_pilots.py`):** Automated live OpenStreetMap Overpass API execution, approval, and `reproduce()` verification for **Maroochydore (`A4-landscape`)**, **Noosa Heads (`A3-landscape`)**, and **Bribie Island — Sandstone Point (`A4-portrait`)**.

### Fixed
- **Commercial Lodging Filtered from Geographic Suburb Titles (`src/maps4u/geo/fetch.py`, `src/maps4u/labels/engine.py`):** Restricted `suburb` labels (`4.5 mm`) to true geographic place types (`suburb`, `locality`, `town`, `hamlet`, `island`, `neighbourhood`, `quarter`), routed scenic `viewpoint`/`attraction`/`peak`/`cape` nodes to `landmarks` (`2.8 mm`), and excluded commercial lodging (`motel`, `hotel`, `hostel`, `guest_house`, `apartment`) from crowding street labels.
- **Unnamed OSM Feature `NaN` Label Filtering (`src/maps4u/labels/engine.py`):** Filtered pandas `float('nan')` names so unnamed ways/polygons never emit literal `"nan"` labels.

---

## [1.0.2] - 2026-10-24 (Production Hardening, Immutable Provenance & Queue Resilience)

### Fixed & Hardened
- **`SEC-001` (Critical — Production Credentials):** Removed hardcoded default operator tokens (`maps4u-prod-operator-token`) from `docker-compose.yml` in favour of mandatory `${MAPS4U_OPERATOR_TOKEN:?...}` and `${MAPS4U_REVIEWER_TOKEN:?...}` injection. Added `validate_production_credentials()` in `src/maps4u/api/deps.py` and factory startup enforcement in `src/maps4u/api/main.py` to refuse startup in `prod`/`staging` if tokens are missing, `< 16` characters, match known default/placeholder values, or are identical.
- **`SEC-002` (High — Verified Reviewer Identities & Separation of Duties):** Removed trust in `X-Operator-Identity` and request-body `reviewer` strings. Bound principal identities strictly to server-configured `MAPS4U_OPERATOR_IDENTITY` and `MAPS4U_REVIEWER_IDENTITY` associated with each authenticated token, requiring a distinct `MAPS4U_REVIEWER_TOKEN` for production approvals/rejections.
- **`SEC-003` (High — Removal of URL Query-String Token Authentication):** Removed `?token=` query-string authentication from `src/maps4u/api/deps.py` and updated `src/maps4u/ui/static/app.js` to fetch artifacts via `Authorization: Bearer` headers (`Blob` object URLs) so credentials never appear in URLs, browser history, or access logs.
- **`DATA-001` (Critical — Immutable Content-Addressed OSM Provenance):** Separated cache lookup identity (`compute_cache_lookup_key(bbox, query)` stored in `<lookup_key>.latest.json`) from content-addressed snapshot identity (`compute_snapshot_id(bbox, query, raw_sha256)`). Switched `osm_snapshots` persistence to `INSERT OR IGNORE` so cache refreshes never overwrite historical `.raw.json` or `.gpkg` files referenced by finalized jobs.
- **`DATA-002` (High — Frozen Reproducibility Inputs):** Archived exact copies of `style.yaml`, `paper_templates.yaml`, and `corrections.yaml` into `artifacts/<job_id>/frozen_inputs/` alongside `gpkg_sha256`, `templates_sha256`, and `render_config` in `manifest.json`, and updated `reproduce()` to verify all input SHA-256 digests (`409 E_STORAGE` on mismatch).
- **`DATA-003` (High — GeoPackage Corruption Detection & Auto-Recovery):** Removed silent empty-layer fallback in `read_geopackage_snapshot()`. Corrupted or missing `.gpkg` layers now automatically rebuild from the SHA-256-verified immutable `.raw.json` snapshot when available, or fail deterministically with `422 E_STORAGE`.
- **`QUEUE-001` (High — Atomic Job Claiming & Duplicate Dispatch Prevention):** Added `try_acquire_job_claim()` / `release_job_claim()` and SQLite atomic conditional state claiming (`WHERE job_id = ? AND status IN ('created', 'queued')`) to prevent duplicate dispatches or concurrent workers executing the same job (`409 E_STATE_ILLEGAL`).
- **`QUEUE-002` (High — Working Retry Execution & Backoff):** Updated `POST /api/jobs/{job_id}/retry` to increment `retry_count`, record `job.retry_requested` audit events with previous failure context, and immediately execute (`inline`) or enqueue (`celery` with exponential backoff `countdown`).
- **`QUEUE-003` (High — Accurate Celery Task Outcomes):** Updated `run_job_task` in `src/maps4u/worker/tasks.py` to distinguish transient errors (`E_OVERPASS_UNAVAILABLE`, `E_OVERPASS_RATE_LIMIT`, `ConnectionError`, `TimeoutError` -> `self.retry(exc=..., countdown=...)`) from terminal errors (`Maps4UError` re-raised so Celery records `FAILURE`).
- **`QA-001` (Medium — Removal of Runtime QA Shortcuts):** Removed the `raw_bytes.strip() == b"ok"` test-stub shortcut from production `verify_governed_qa_and_pdf()` in `src/maps4u/core/state.py`.
- **`OPS-001` (Medium — Deep Operational Readiness Probe):** Upgraded `GET /readyz` in `src/maps4u/api/routes_system.py` to verify SQLite schema readiness and, when `MAPS4U_QUEUE=celery`, Redis broker `PING` and active Celery worker `control.inspect().ping()`, returning `503` when any required dependency is unhealthy.

---

## [1.0.1] - 2026-10-23 (Smoke Test, Defect Remediation & Regression Hardening)

### Fixed
- **`BUG-001` (P0 — Runtime Dependencies):** Declared `PyPDF2>=3.0.0`, `Pillow>=10.0.0`, `pycairo>=1.26.0`, `reportlab>=4.1.0`, and `pyproj>=3.6.0` as direct runtime dependencies in `pyproject.toml`.
- **`BUG-002` (P0 — Installation-Safe Resource Paths):** Packaged `config/`, `schemas/`, and `styles/` inside `src/maps4u/resources/` and added `resolve_resource_path()` in `src/maps4u/core/config.py` so templates, style packs, and JSON schemas resolve cleanly from site-packages or explicit `MAPS4U_*_DIR` settings without relying on `parents[3]`.
- **`BUG-003` (P0 — API Authentication & RBAC):** Enforced Bearer / `X-Operator-Token` / `X-Reviewer-Token` authentication (`hmac.compare_digest`), fail-closed `503 E_FORBIDDEN` in `prod`/`staging` when tokens are unconfigured, operator vs. reviewer role separation, and verified reviewer identity recording.
- **`BUG-004` (P1 — Celery Worker Execution):** Connected `POST /api/jobs/{job_id}/run` to `run_job_task.apply_async` when `MAPS4U_QUEUE=celery` (`created -> validating -> queued`) and implemented full `execute_job_pipeline` execution inside `src/maps4u/worker/tasks.py`.
- **`BUG-005` (P1 — Redis Environment Variable Alignment):** Standardised `MAPS4U_REDIS_URL` and `REDIS_URL` via `AliasChoices` in `Settings` (`src/maps4u/core/config.py`), `docker-compose.yml`, and `.env.example`.
- **`BUG-006` (P1 — Duplicate Job Submission Protection):** Replaced `INSERT OR REPLACE INTO jobs` with conflict checking (`409 E_STATE_ILLEGAL`) so existing/finalized jobs can never be silently reset, and added `POST /api/jobs/{job_id}/reproduce` + `POST /api/jobs/{job_id}/retry`.
- **`BUG-007` (P1 — Project-Scoped Geofence Revision IDs):** Scoped `revision_id` as `SHA-256(project_id:geometry_sha256)` while preserving `geometry_sha256` and replacing destructive `INSERT OR REPLACE` with `INSERT OR IGNORE`.
- **`BUG-008` (P1 — QA Gate Enforcement on `proof_ready` & Approval):** Gated `proof_ready` and `finalized` transitions on a persisted `qa-report.json` (`passed == True`, `blocker_count == 0`) and structurally valid `%PDF-` 1-page `proof.pdf` matching `manifest.json`.
- **`BUG-009` (P1 — Unexpected Pipeline Exception Handling):** Wrapped stage execution in `PipelineRunner` (`src/maps4u/worker/pipeline.py`) to catch arbitrary exceptions, transition jobs to `failed` with `E_PIPELINE_FAILED`, and permit controlled retries (`failed -> queued`).
- **`BUG-010` & `BUG-011` (P2 — CI Workflow & Makefile):** Fixed `Makefile` tab recipe prefixes and `--factory` Uvicorn invocation (`maps4u.api.main:create_app`), and expanded CI workflow with wheel packaging, maintenance drills, and Docker Compose smoke checks.
- **`BUG-012` (P2 — Settings Field Name Compatibility):** Enabled `populate_by_name=True` on `Settings` and updated `scripts/smoke_test.py`, `scripts/verify_determinism.py`, and `scripts/backup_restore_drill.py`.
- **`BUG-013` (P2 — Style Resolution & Render Settings):** Added `load_style_by_ref()` with path-traversal protection and schema validation, rejected unknown styles with `422 E_STYLE_INVALID`, and wired `maps4u_min_font_mm` and `maps4u_insets_enabled` through composition and QA.
- **`BUG-014` (P2 — Complete Browser Operator Journey):** Upgraded `src/maps4u/ui/static/{index.html,app.js,styles.css}` with auth token/identity inputs, error banner, job run/refresh/reproduce controls, artifact download/preview buttons, approve/reject sign-off, and YAML corrections submission.
- **`BUG-015` (P2 — Concurrency, Cache Ageing & Tamper Detection):** Enforced `BoundedSemaphore(MAPS4U_OVERPASS_MAX_CONCURRENCY)` in `OverpassClient`, `MAPS4U_CACHE_MAX_AGE_DAYS` expiry in `lookup_cached_snapshot()`, and SHA-256 verification against `manifest.json` and `review_decisions.proof_sha256` on every artifact download.

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
