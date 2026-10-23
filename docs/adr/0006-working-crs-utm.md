# ADR-0006: Metric Working CRS via Dynamic Centroid UTM Zone

- **Status:** Accepted (Stage 1 Gate `G1` / Stage 2 Gate `G2`)
- **Date:** 2026-10-21
- **Owners:** MAPS4U Engineering

## Context
Web Mercator (`EPSG:3857`) introduces latitude-dependent scale distortion that invalidates true print scale (`1:N`) and physical millimetre (`mm`) calculations.

## Decision
Store geofences and cached snapshots in `EPSG:4326` (`WGS84`), and dynamically project geometries to the geofence centroid's metric UTM zone (`maps4u.geo.crs.utm_crs_for_lonlat`, e.g., `EPSG:32756` for Southeast Queensland) for all area validation, print scale calculation, geometry simplification, and physical sheet projection.

## Verification
- `tests/unit/test_templates_and_assess.py`
