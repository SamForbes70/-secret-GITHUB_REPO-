# Maps4U Pilot QA & Cartographic Acceptance Report (`S5.T3` — Gate `G5`)

## 1. Pilot Areas Evaluated

| Pilot Area | Paper & Orientation | Scale Band | QA Verdict | Blockers | Overlaps | Clipped Labels | Min Font Height | Reproducibility (`reproduce()`) |
|---|---|---|---|---|---|---|---|---|
| **Maroochydore (MCY)** | `A4-landscape` | `standard_street` (`1:12,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (100% content & PDF SHA-256 match) |
| **Noosa** | `A3-landscape` | `detail` (`1:7,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (100% content & PDF SHA-256 match) |
| **Bribie Island / Sandstone Point** | `A4-portrait` | `standard_street` (`1:12,500`) | **PASS** | `0` | `0` | `0` | `>= 1.50 mm` | **PASS** (100% content & PDF SHA-256 match) |

## 2. Governed Output Bundle Verification

Every pilot job transitioned to `proof_ready` only after server-side verification (`verify_governed_outputs`) confirmed all 5 governed outputs (`proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, `manifest.json`) were non-empty and cryptographically linked in `bundles` and `manifest.json`.

## 3. Review & Immutability Verification

- `POST /api/jobs/{job_id}/approve` locks the proof SHA-256 in `review_decisions` and transitions the job to `finalized`.
- `POST /api/jobs/{job_id}/reject` enforces non-empty reviewer comment (`422` on blank comment) and records the rejection in `review_decisions`.
- `POST /api/jobs/{job_id}/corrections` validates YAML corrections against `schemas/corrections.schema.json` and spawns a new child job without mutating the approved/rejected parent job or cached `.gpkg` snapshot.
