# ADR-0007: Governed 5-Artifact Output Bundle Enforcement

- **Status:** Accepted (Stage 4 Gate `G4` / Stage 5 Gate `G5`)
- **Date:** 2026-10-22
- **Owners:** MAPS4U Engineering

## Context
Operators must never review or approve an incomplete render job lacking its QA preflight report, preview thumbnail, or cryptographic provenance manifest.

## Decision
`maps4u.core.state.transition_job_state` enforces `verify_governed_outputs(artifact_dir, job_id)` before allowing any job to enter `proof_ready`. All 5 files (`proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, `manifest.json`) must exist on disk and be non-empty, or the transition fails with `409 E_GOVERNED_OUTPUT_MISSING`.

## Verification
- `tests/unit/test_state_and_db.py`
- `tests/integration/test_stage4_qa_and_bundle.py`
