# Maps4U Pilot QA & Cartographic Acceptance Report (`v1.0.0-mvp` — Gate `G5` / `G6`)

## 1. Multi-Pilot Acceptance Matrix

All three Queensland coastal pilot areas were executed through the full 11-stage governed pipeline (`execute_job_pipeline`) and re-verified via `reproduce(job_id)`:

| Pilot Area | Paper & Orientation | Scale Band | QA Verdict | Blockers | Overlaps | Clipped Labels | Min Font Height | Reproducibility (`reproduce()`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Maroochydore (MCY)** | `A4-landscape` (`297×210 mm`) | `standard_street` (`1:12,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (`matched: true`, byte-identical PDF SHA-256) |
| **Noosa** | `A3-landscape` (`420×297 mm`) | `detail` (`1:7,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (`matched: true`, byte-identical PDF SHA-256) |
| **Bribie Island / Sandstone Point** | `A4-portrait` (`210×297 mm`) | `standard_street` (`1:12,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (`matched: true`, byte-identical PDF SHA-256) |

---

## 2. 7-Gate Automated QA Preflight Verification (`src/maps4u/qa/preflight.py`)

Every job must pass all 7 automated QA gates before operator approval:

1. **`PDF_PAGE_SIZE`:** Verified `MediaBox`, `TrimBox`, and `BleedBox` (`+3.0 mm` bleed) match `config/paper_templates.yaml`.
2. **`PDF_VECTOR_PATHS`:** Confirmed true vector path operators (`m`, `l`, `S`, `f`) with zero raster map tiles.
3. **`PDF_FONTS_EMBEDDED`:** Confirmed embedded TrueType font descriptors (`DejaVuSans`, `DejaVuSans-Bold`).
4. **`ODBL_ATTRIBUTION`:** Confirmed `© OpenStreetMap contributors (ODbL)` is present in both composed furniture and the PDF stream.
5. **`EMPTY_MAP_ROADS`:** Confirmed `DrawPlan` contains rendered road primitives.
6. **`MIN_FONT_HEIGHT`:** Confirmed every placed label has printed cap height `>= 1.50 mm`.
7. **`LABEL_COLLISION` & `LABEL_CLIPPED`:** Confirmed `0` intersecting label bounding boxes and `0` labels extending outside `map_area_mm`.

---

## 3. Governed Output Bundle & Review Immutability

- **5 Governed Outputs Enforced:** `verify_governed_outputs()` confirms `proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, and `manifest.json` exist and are non-empty before transitioning to `proof_ready`.
- **Cryptographic Approval Lock:** `POST /api/jobs/{job_id}/approve` records `proof_sha256` in `review_decisions` and locks the job in `finalized`.
- **Mandatory Rejection Comment:** `POST /api/jobs/{job_id}/reject` enforces a non-blank reviewer comment (`422 E_CORRECTIONS_INVALID` on blank input).
- **Non-Destructive Client Corrections:** `POST /api/jobs/{job_id}/corrections` validates YAML against `schemas/corrections.schema.json` and spawns a linked child job without mutating the parent job or `.gpkg` snapshot.

---

## 4. Live OpenStreetMap Overpass 3-Area Pilot Verification (`Stage 5.T3` / `Stage 6.T3`)

Executed via `python -m scripts.run_live_pilots` against `https://overpass-api.de/api/interpreter` in `prod` mode with content-addressed `.gpkg` caching and `POST /api/jobs/{job_id}/reproduce` verification:

| Pilot Area | Format | Scale | Overpass Payload | Extracted Features (`roads` / `parks` / `water`) | Snapshot SHA-256 (`snapshot_id`) | Locked `proof.pdf` SHA-256 | `reproduce()` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Maroochydore** | `A4-landscape` | `1:12,500` | `1,043,737 B` | `1,309` roads, `16` parks, `11` water, `3` coastline, `8` places, `1` landmark | `bfcbfdc8a483c041...` | `bb45105dcd066ac9...` | **MATCHED (`true`)** |
| **Noosa Heads** | `A3-landscape` | `1:7,500` | `386,763 B` | `413` roads, `13` parks, `5` water, `2` coastline, `11` places, `1` landmark | `9073792a0d192388...` | `c89d130a7512ae29...` | **MATCHED (`true`)** |
| **Bribie Island — Sandstone Point** | `A4-portrait` | `1:10,000` | `368,274 B` | `334` roads, `8` parks, `1` water, `2` coastline | `3c3d52bb699c48bd...` | `51c943dc19f16843...` | **MATCHED (`true`)** |
