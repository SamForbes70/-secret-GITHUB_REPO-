# Maps4U Street Map System (`maps4u-maps` v1.0.0-mvp)

Deterministic cartographic street-map production pipeline that converts an operator-drawn geofence and paper selection (`A3`, `A4`, `A5` in `landscape` or `portrait`) into a print-ready vector PDF street map (`proof.pdf`), raster thumbnail (`thumb.png`), QA preflight report (`qa-report.json` + `qa-report.md`), and cryptographic provenance manifest (`manifest.json`), styled after the Maroochydore (`MCY`) reference sheet.

## Key Capabilities
- **6 Paper Templates (`config/paper_templates.yaml`):** `A3`, `A4`, `A5` in `landscape` and `portrait` with 3.0 mm bleed, safe margins, and automated furniture zones.
- **Print-Scale & Font Legibility Engine (`POST /api/viability`):** Projects WGS84 geofences to UTM (`EPSG:32756`), calculates natural and standard print scales (`1:N`), and blocks non-overridably if any mandatory label falls below the `1.5 mm` minimum printed height.
- **OSM Overpass Fetch & 8-Layer GeoPackage Cache:** Deterministic Overpass QL queries, SHA-256 snapshot caching (`roads`, `water`, `water_lines`, `parks`, `boundaries`, `coastline`, `places`, `landmarks`), and non-destructive YAML client corrections (`apply_corrections`).
- **YAML Cartographic Style Engine (`styles/mcy/v1/style.yaml`):** Scale-band road hierarchy casings/fills, hydrography, parks, boundaries, and strict z-order rendering.
- **Deterministic `STRtree` Label Placement & Map Furniture:** Priority-ranked street/suburb/landmark/water/park labels with zero overlaps, repeated arterial labels, alphanumeric grid (`A1..H6`), street index, scale bar, north arrow, legend, and mandatory ODbL attribution.
- **Governed Proof Review & Reproducibility (`reproduce()`):** Every job reaches `proof_ready` only after all 5 governed outputs pass verification; approvals lock `proof_sha256` in `review_decisions`.
