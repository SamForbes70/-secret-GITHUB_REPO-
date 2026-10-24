# Maps4U Testing, TDD & Verification Guide (`v1.0.2`)

## 1. Core Testing Principles

- **Strict TDD First (`C-3`):** Every stage (Gates `G1` through `G6`) was built test-first (RED → GREEN → REFACTOR).
- **100% Offline Automated Execution:** All unit, property-based, API, and integration tests execute without external network calls using recorded Overpass fixtures (`tests/fixtures/overpass/mcy_sample.json`) and `MAPS4U_QUEUE=inline`.
- **Byte-Identical Determinism Verification:** Repeated runs on identical frozen inputs are asserted to produce identical `proof.pdf` SHA-256 digests and identical `content_hash()` draw logs.

---

## 2. Test Suite Architecture (94 Tests Across 16 Modules)

| Tier | Test File | Coverage & Invariants Verified |
| :--- | :--- | :--- |
| **Unit & Property** | `tests/unit/test_fetch_roads_bbox.py` | Overpass QL builder, retry/backoff ladder, 8-layer GeoPackage parsing (`roads`, `water`, `parks`, etc.). |
| **Unit & Property** | `tests/unit/test_corrections.py` | YAML schema validation, `rename`, `reclass`, `add`, `remove`, and immutability of cached `.gpkg`. |
| **Unit & Property** | `tests/unit/test_state_and_db.py` | SQLite WAL schema, legal/illegal state transitions (`E_STATE_ILLEGAL`), and governed output gate (`E_GOVERNED_OUTPUT_MISSING`). |
| **Unit & Property** | `tests/unit/test_templates_and_assess.py` | All 6 paper templates (`A3`/`A4`/`A5`), Hypothesis monotonicity of scale calculation, and `1.5 mm` minimum font blocker. |
| **Unit & Property** | `tests/unit/test_stage3_canvas_and_style.py` | `styles/mcy/v1/style.yaml` validation, z-order monotonicity, two-pass road casings/fills, and `CairoCanvas` determinism. |
| **Unit & Property** | `tests/unit/test_stage4_labels_and_furniture.py` | `STRtree` zero-collision label placement, upright angles (`[-90°, +90°)`), grid references (`A1..H6`), street index, and ODbL attribution. |
| **API** | `tests/api/test_api_phase0.py` | `/healthz`, `/readyz`, `/api/meta`, `/api/styles`, `/api/projects`, geofence validation, and job creation. |
| **API** | `tests/api/test_stage2_viability_and_ui.py` | `/api/templates`, `/api/viability`, remediation suggestions, and static Leaflet UI serving (`GET /`). |
| **API** | `tests/api/test_stage5_jobs_and_review.py` | Full job execution (`/run`), artifact downloads, approval `proof_sha256` locking, blank-comment rejection (`422`), and `/corrections` child job spawning. |
| **Integration** | `tests/integration/test_acquire.py` | End-to-end Overpass fixture acquisition and `.gpkg` cache hit reuse. |
| **Integration** | `tests/integration/test_stage3_proof_render.py` | Maroochydore `A4-landscape` vector PDF structural checks and golden determinism. |
| **Integration** | `tests/integration/test_stage4_qa_and_bundle.py` | 7-gate QA preflight report (`qa-report.json`/`.md`), blocker detection, and `manifest.json` bundle creation. |
| **Integration** | `tests/integration/test_stage5_reproducibility_and_pilots.py` | `reproduce()` verification and 3-pilot acceptance (**Maroochydore**, **Noosa**, **Bribie Island**). |
| **Integration / UAT** | `tests/integration/test_stage6_packaging_and_handover.py` | `Dockerfile` & `docker-compose.yml` validation, handover docs completeness, online SQLite backup/restore drill, and full UAT operator journey. |
| **Regression (`v1.0.1`)** | `tests/integration/test_v101_defect_remediation.py` | 23 regression checks covering `BUG-001` through `BUG-015` (wheel isolation, RBAC, Celery dispatch, duplicate job `409` race, scoped geofence revisions, QA gates, all 10 stage exceptions, style validation, UI journey, Overpass semaphore, cache TTL, and artifact tamper detection). |
| **Hardening (`v1.0.2`)** | `tests/integration/test_v102_production_hardening.py` | 11 regression checks covering `SEC-001..003`, `DATA-001..003`, `QUEUE-001..003`, `QA-001`, and `OPS-001` (fail-closed prod credentials, unforgeable reviewer identity, URL token rejection, content-addressed OSM provenance, frozen reproducibility inputs, GeoPackage corruption recovery, atomic job claiming, retry execution/backoff, Celery transient vs. terminal errors, and deep `/readyz`). |

---

## 3. Running Tests & Verification Scripts

```bash
# Run all 94 offline tests
make test

# Run with line coverage report
make test-cov

# Run ruff linter and mypy type checker
make lint

# Run standalone determinism verification script
python scripts/verify_determinism.py

# Run online SQLite WAL + artifact backup/restore drill
python -m scripts.backup_restore_drill
```
