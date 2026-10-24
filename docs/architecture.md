# Maps4U System Architecture (`v1.0.2`)

## 1. Architectural Overview

The **Maps4U Street Map System** (`maps4u-maps`) is a deterministic, containerised cartographic pipeline that converts an operator-drawn geofence (`EPSG:4326`) and print paper specification (`A3`, `A4`, `A5` in `landscape` or `portrait`) into a governed 5-artifact proof bundle.

### Runtime Profiles
- **Pilot / MVP Profile (`v1.0.0-mvp`, Active):**
  - **API & Static UI:** FastAPI (`src/maps4u/api/`) serving REST endpoints and the vendored Leaflet operator console (`src/maps4u/ui/static/`).
  - **Execution Queue:** Celery + Redis 7 (`MAPS4U_QUEUE=celery`) in Docker production mode, or synchronous in-process execution (`MAPS4U_QUEUE=inline`) for local development and deterministic offline testing.
  - **State & Audit Persistence:** SQLite in `WAL` mode (`maps4u.db` / `maps4u.sqlite3`) with foreign-key enforcement (`PRAGMA foreign_keys = ON`) paired with an append-only `audit.jsonl` event stream.
  - **Geospatial Snapshot Cache:** 8-layer OpenStreetMap GeoPackage (`.gpkg`) snapshots alongside raw Overpass JSON response bytes keyed by SHA-256.
  - **Vector Renderer:** `CairoCanvas` (`src/maps4u/render/cairo_canvas.py`) emitting deterministic PDF 1.4 vector streams (`proof.pdf`), canonical draw-logs (`drawlog.json`), and Pillow raster previews (`thumb.png`).
- **Stage 7 Production Profile (Gated Future Extension):**
  - PostgreSQL/PostGIS state store, S3-compatible object storage with signed artifact URLs, and OIDC operator authentication.

---

## 2. Component & Module Architecture

| Package | Key Modules | Architectural Responsibility |
| :--- | :--- | :--- |
| `maps4u.core` | `config.py`, `db.py`, `state.py`, `ids.py`, `errors.py`, `logging.py`, `schemas.py` | Runtime configuration (`Settings`), SQLite WAL session management & schema migrations, 11-stage governed job state machine, canonical JSON hashing (`spec_id`), structured domain errors (`Maps4UError`), and JSONL audit logging. |
| `maps4u.geo` | `crs.py`, `overpass.py`, `fetch.py`, `cache.py`, `acquire.py`, `features.py`, `corrections.py` | Geofence topology & area validation (`<= 600 km²`, `<= 200` vertices/ring), dynamic centroid UTM projection (`EPSG:32756` for SE Queensland), Overpass QL query builder, rate-limited HTTP/file fetcher, 8-layer `.gpkg` snapshot cache, and non-destructive YAML client corrections. |
| `maps4u.layout` | `templates.py`, `furniture.py` | Loads `config/paper_templates.yaml` (`A3`/`A4`/`A5` × `landscape`/`portrait`), resolves bleed (`3.0 mm`), margins, map viewport, alphanumeric reference grid (`A1..H6`), multi-column street index, graphic scale bar, north arrow, legend, title block, and mandatory ODbL attribution. |
| `maps4u.render` | `assess.py`, `style_engine.py`, `canvas.py`, `cairo_canvas.py`, `proof_renderer.py` | Pre-job print scale & minimum font legibility viability assessment (`>= 1.5 mm`), YAML style loading & JSON Schema validation (`styles/mcy/v1/style.yaml`), two-pass road casing/fill draw-plan builder, and deterministic vector PDF + PNG rendering. |
| `maps4u.labels` | `engine.py` | Priority-ranked (`suburb` → `landmark` → `arterial` → `collector` → `local` → `service`), collision-free label placement using Shapely `STRtree`, upright angle normalization (`[-90°, +90°)`), and arterial repeat spacing (`120 mm`). |
| `maps4u.qa` | `preflight.py` | Automated 7-gate cartographic QA preflight engine verifying PDF MediaBox dimensions, vector path operators, embedded font descriptors, ODbL attribution, road presence, minimum font height (`>= 1.5 mm`), zero label collisions, and zero frame clipping. |
| `maps4u.bundle` | `archive.py` | Writes cryptographic `manifest.json`, records `bundles` rows in SQLite, and implements `reproduce(job_id)` to re-verify byte-for-byte deterministic output from frozen inputs. |
| `maps4u.worker` | `celery_app.py`, `tasks.py`, `executor.py`, `pipeline.py` | Orchestrates the 11-stage job execution pipeline (`execute_job_pipeline`) both synchronously (`inline`) and asynchronously via Celery. |
| `maps4u.api` | `main.py`, `routes_system.py`, `routes_styles.py`, `routes_projects.py`, `routes_viability.py`, `routes_jobs.py` | FastAPI application factory, REST endpoints, static UI mounting, and global `Maps4UError` -> HTTP JSON exception handling. |

---

## 3. Governed 11-Stage Job State Machine

Enforced in `src/maps4u/core/state.py` (`LEGAL_TRANSITIONS`). Every transition is recorded in both the SQLite `job_events` table and `<MAPS4U_DATA_DIR>/audit.jsonl`.

```text
created
  └──> validating
         └──> queued
                └──> assessing
                       └──> acquiring
                              └──> transforming
                                     └──> styling
                                            └──> labelling
                                                   └──> composing
                                                          └──> rendering
                                                                 └──> verifying
                                                                        └──> proof_ready
                                                                               ├──> finalized (via POST /approve; locks proof_sha256)
                                                                               └──> rejected  (via POST /reject; requires comment)
```

- Any active pipeline stage may transition to `failed` (storing `error_code` and `error_detail`), and a `failed` job may be retried via `POST /api/jobs/{job_id}/retry` (`failed` → `queued`).
- **Hard Governance Gate (`verify_governed_outputs`):** Transitioning from `verifying` to `proof_ready` is rejected with `409 Conflict` (`E_GOVERNED_OUTPUT_MISSING`) unless all 5 governed files (`proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, `manifest.json`) exist on disk and have size `> 0`.
- **Terminal Immutability:** Once a job reaches `finalized` or `rejected`, no further state transitions are permitted (`E_STATE_ILLEGAL`). Subsequent client YAML corrections spawn a new child job with its own `spec_id` and `job_id`.

---

## 4. Coordinate Reference Systems (CRS)

1. **Storage & API Boundary CRS (`EPSG:4326` / WGS84):**
   - All geofence revisions (`geofence_revisions.geometry_json`), Overpass bounding boxes, and cached GeoPackage (`.gpkg`) layers are stored in standard `EPSG:4326` (`[lon, lat]`).
2. **Metric Working CRS (Dynamic Centroid UTM, e.g., `EPSG:32756`):**
   - Computed via `maps4u.geo.crs.utm_crs_for_lonlat(lon, lat)` from the geofence centroid.
   - Used for all metric area calculations (`km²`), scale denominator (`1:N`) math, simplification tolerances (`m`), and physical sheet projection (`mm`).
3. **Sheet Coordinate System (`mm`):**
   - Origin `(0, 0)` at bottom-left of trim box (`page_mm`), with `3.0 mm` bleed extending outward to `[-3.0, -3.0, W+3.0, H+3.0]`.

---

## 5. SQLite WAL Database Schema (`0001_initial.sql`)

| Table | Primary Key | Description |
| :--- | :--- | :--- |
| `map_projects` | `project_id` | Top-level named map project (`area_name`, `reference`, `notes`). |
| `geofence_revisions` | `revision_id` | Immutable canonicalised WGS84 GeoJSON revisions (`is_current` flag). |
| `render_specifications` | `spec_id` | Frozen canonical JSON render specification (`seed: 0`, `paper`, `orientation`, `style_ref`, `corrections_id`). |
| `jobs` | `job_id` | Job execution state, computed `scale_denominator`, `min_font_mm`, and error metadata. |
| `job_events` | `id` | Append-only state transition log per job (`ts`, `stage`, `event`, `payload_json`). |
| `osm_snapshots` | `snapshot_id` | Provenance record for cached Overpass extracts (`bbox`, `raw_path`, `gpkg_path`, `sha256`). |
| `corrections_files` | `corrections_id` | Registered client YAML correction files and their SHA-256 digests. |
| `style_versions` | `style_ref` | Registered YAML style versions and their SHA-256 digests. |
| `bundles` | `bundle_id` | Governed output bundle manifest and `output_sha256` (`proof.pdf` SHA-256). |
| `qa_results` | `job_id` | Summary QA preflight metrics (`min_font_ok`, `overlaps`, `clipped`, `dropped_json`). |
| `qa_findings` | `finding_id` | Individual QA preflight findings (`blocker`, `warning`, `info`). |
| `review_decisions` | `decision_id` | Cryptographically locked operator review decisions (`approved` / `rejected`, `reviewer`, `comment`, `proof_sha256`). |
| `schema_migrations` | `version` | Applied SQL schema migration versions. |
