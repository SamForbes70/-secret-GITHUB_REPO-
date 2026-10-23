# ADR-0008: Immutable Geofence Revisions and Frozen Render Specifications

- **Status:** Accepted (Stage 1 Gate `G1` / Stage 5 Gate `G5`)
- **Date:** 2026-10-21
- **Owners:** MAPS4U Engineering

## Context
Cryptographic auditability requires that approved proofs be permanently tied to the exact geofence geometry, paper template, style version, and client corrections used to produce them.

## Decision
1. Geofence edits create immutable `geofence_revisions` rows hashed by canonical GeoJSON.
2. Job creation freezes a `render_specifications` record (`spec_id`) hashed by canonical JSON.
3. Submitting client YAML corrections (`POST /api/jobs/{job_id}/corrections`) creates a new child job with a new `spec_id`, leaving the parent job immutable.

## Verification
- `tests/api/test_stage5_jobs_and_review.py`
