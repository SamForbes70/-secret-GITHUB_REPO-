# ADR-0005: Overpass Fair-Use Rate Limiting, Raw-Bytes Provenance & Offline Fixture Mode

- **Status:** Accepted (Stage 1 Gate `G1`)
- **Date:** 2026-10-21
- **Owners:** MAPS4U Engineering

## Context
Public Overpass API endpoints enforce strict rate limits, and automated CI/CD test suites must never depend on live external network calls.

## Decision
1. Enforce `MAPS4U_OVERPASS_MAX_CONCURRENCY=1` with a deterministic retry backoff ladder (`10s`, `30s`, `90s`).
2. Persist raw Overpass response bytes (`raw_path`) and compute their SHA-256 digest before parsing into the 8-layer `.gpkg` snapshot.
3. Support `file://` URLs in `MAPS4U_OVERPASS_URL` so all automated tests run 100% offline against recorded fixtures (`tests/fixtures/overpass/mcy_sample.json`).

## Verification
- `tests/unit/test_fetch_roads_bbox.py`
- `tests/integration/test_acquire.py`
