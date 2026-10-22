# Maps4U Map Production Automation (MPA) — Product Requirements Document v2

**Status:** Draft PRD (revised scope — street maps only, no advertising/QR)  
**Prepared by:** August  
**Date:** 2026-07-11  
**Stakeholder:** Sam Forbes / Maps4U  

---

## 1. What changed

After receiving David’s follow-up, the scope for this **first machine** is now strictly **street map production**. Advertising, QR codes, M2G and DDD are explicitly out for the MVP. The goal is to make it dead easy to:

1. Pull a new map area up on screen.
2. Draw a geofence around the intended print area.
3. Let the system calculate whether the area can be rendered legibly at the chosen paper size, primarily by checking minimum font size.
4. Generate a **print-ready, vector PDF** of the street map in a style derived from the Maroochydore (MCY) reference map.

The business value is automating the most painful, manual, expensive part of creating a new map area. Once this works reliably, ad/QR/self-service layers can be layered on later without touching the cartographic core.

---

## 2. Machine’s purpose

A repeatable, deterministic pipeline that turns a geofenced boundary and a paper-size choice into a **reviewable, print-ready vector PDF street map**, preserving the established Maps4U look and resolving the detail-vs-legibility conflict that broke earlier AI attempts.

---

## 3. What the machine must do

1. **Accept a geographic job:** area name, geofence/Polygon bounds, paper size (A3/A4/A5, orientations), edition info, reference style version.
2. **Fetch/cached OpenStreetMap data** for roads, paths, lanes, waterways, parks/reserves, suburb boundaries, named places, landmarks.
3. **Apply the Maps4U cartographic style** derived from the MCY reference PDF (colours, line weights, road hierarchy, water/park fills, suburb labels, map keys).
4. **Resolve detail vs. legibility** using print-scale rules. Not every label needs to appear, and the system must warn when minimum font size would be breached.
5. **Produce a single-page or multi-page/inset option** when one page cannot be both complete and legible. Insets may go on the back of the map if required.
6. **Compose all map furniture** — title, legend, scale bar, north arrow, grid, copyright/attribution, ODbL credit — controlled by templated configuration.
7. **Generate a vector PDF proof** with selectable text and sharp linework.
8. **Report on quality/legibility** — dropped labels, suspected omissions, minimum font size issues, clipped features — so a non-technical reviewer can approve or request changes.
9. **Support local corrections** as a file the client can update on their laptop and the system can re-ingest into a future run.
10. **Archive a reproducibility bundle** — job definition, OSM data snapshot, style version, renderer version, output PDF — so the same map can be regenerated later.

---

## 4. Explicitly out of scope (MVP)

- Advertising layout, slots, artwork or QR codes.
- M2G / Google Business Profile / DDD integration.
- Online self-service portal for end-customers.
- Automatic style extraction from the reference PDF by AI — v1 style values will be measured manually from the MCY PDF and encoded into a style spec file.
- Multi-page atlases beyond a front map plus optional inset/back page.

---

## 5. How the machine does it

### 5.1 Components

| Layer | Component | Responsibility | Candidate tech |
|---|---|---|---|
| **Orchestrator** | FastAPI + Celery/Redis | Receive jobs, queue work, track state, emit proof PDF | `fastapi`, `celery`, `redis` |
| **Geo data** | OSM cache | Fetch from Overpass / osmnx; cache to Geopackage or PostGIS; record source/time | `osmnx`, `overpy`, `geopandas`, `fiona`, `shapely` |
| **Cartographic engine** | Style rules + feature selection | Classify roads, water, parks, boundaries; scale-dependent selection; label candidates | Mapnik via Python bindings, custom Shapely, matplotlib fallback |
| **Text/label engine** | Label placement | Priority-based label inclusion, collision detection, multi-position candidates, edge-safe | Custom Python with Shapely/FreeType font-metrics |
| **Layout composer** | Page builder | Map viewport, margins, legend, title, scale, north arrow, grid, attribution; A3/A4/A5 templates | Python + SVG / Cairo / ReportLab |
| **Preflight QA** | Legibility checks | Minimum font size per printed mm, clipped labels, dropped-street list, vector/raster verification | fonttools, reportlab PDF analysis |
| **Review UI** | Proof viewer | Show PDF proof + exception report; approve/reject/request-edit | Simple Next.js or Streamlit app |
| **Artifact store** | Storage | Jobs, snapshots, proofs, final PDFs, reproducibility bundle | Local filesystem / S3 / MinIO |
| **Audit log** | Reproducibility | Job JSON, data SHA, style/renderer version, output checksum | SQLite / JSONL |

### 5.2 Simplified workflow

```
Create job (area + paper size + orientation)
  ↓
Resolve bounding box and map scale
  ↓
Fetch OSM data (cache if available)
  ↓
Apply cartographic style and feature selection
  ↓
Generate label candidates and resolve collisions
  ↓
Calculate minimum printable font size
  ↓
If font size < threshold → flag warning / suggest larger paper / split / inset
  ↓
Compose page with furniture
  ↓
Render vector PDF proof
  ↓
Run QA checks → exception report
  ↓
Human review → approve / reject / request change
  ↓
Finalise and archive reproducibility bundle
```

### 5.3 Geofence + legibility

The most important user-interaction requirement from the new information:

- The user draws a geofence on a preview map (e.g., Leaflet/MapLibre).
- The system computes the scale implied by fitting the bounds to the chosen paper size and print margins.
- It then computes the minimum text height at that scale for the smallest intended label size.
- If the computed size falls below the configured threshold (e.g., 1.5 mm when printed), the system immediately warns and offers:
  1. Larger paper size (if available),
  2. Smaller geographic area,
  3. Accept reduced street-name density,
  4. Produce an inset or split layout.

This prevents the “generalisation trap” that broke the earlier AI attempts — the system does not silently drop detail; it either fits it or explicitly tells the user it cannot.

### 5.4 Local corrections file

A simple YAML/GeoJSON corrections file the client can edit on their laptop:

```yaml
corrections:
  - feature: road
    osm_id: 123456789
    action: rename
    name: "The Esplanade"
  - feature: place
    lat: -26.3992
    lon: 153.0894
    action: add
    name: "Sunshine Beach Headland"
    type: landmark
```

The system records the corrections file hash and reapplies it automatically on the same area.

---

## 6. Detailed requirements

### 6.1 Job definition schema (simplified)

```json
{
  "job_id": "maroochydore-2026-07-ed1",
  "area": {
    "name": "Maroochydore",
    "geofence": { "type": "Polygon", "coordinates": [...] },
    "preferred_crs": "EPSG:4326"
  },
  "output": {
    "paper": "A3",
    "orientation": "landscape",
    "vector": true,
    "dpi": 300
  },
  "style": {
    "reference": "MCY-reference.pdf",
    "version": "1.0.0"
  },
  "corrections_file": "optional-path-to-corrections.yaml",
  "metadata": {
    "edition_date": "2026-07-11"
  }
}
```

### 6.2 Data requirements

- Use OpenStreetMap via Overpass API.
- Cache fetched data keyed by bounding box + source tag + timestamp.
- Record data provenance + ODbL attribution.
- Supported feature classes: roads (motorway → service/path), water, parks/reserves, built-up area / suburb boundary, coastline, named places/landmarks.

### 6.3 Style and cartography

- Derive an initial ruleset from the MCY reference PDF by measurement (colours, line weights, font families/sizes, road hierarchy).
- Store style in a version-controlled YAML or JSON file, not hard-coded Python.
- Render with vector output (PDF) as first-class target.
- Support A3, A4, A5; landscape and portrait; each paper size/orientation has its own template.

### 6.4 Labels

- Label every street **that can remain legible** at the chosen scale.
- Generate repeated labels along long roads.
- Resolve or flag collisions.
- Drop lower-priority labels before dropping higher-priority ones, and report the list.
- Ensure no labels clipped by page edge.

### 6.5 Map furniture

- Title block (area name, edition).
- Scale bar (metric; imperial optional).
- North arrow.
- Legend keyed to the style spec.
- Grid / street index grid if desired.
- Copyright / ODbL attribution.
- Date / edition note.

### 6.6 QA/preflight

- Minimum printed font size ≥ threshold (configurable, default 1.5 mm).
- Label overlap count and list.
- Clipped label list.
- Dropped street names and reason (e.g., collision, scale).
- Vector/raster check on final PDF.
- Missing feature classes for the area.

### 6.7 Review workflow

- Output a proof PDF + QA report.
- Reviewer can open the PDF without any dev tools.
- Simple UI or even just a folder with `proof.pdf` + `qa-report.md` is acceptable for MVP.
- Approve → lock reproducibility bundle → final PDF.

---

## 7. Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| Job API / orchestrator | FastAPI + Celery | Already loaded as skills; good for async map jobs |
| OSM fetch | osmnx + overpy | Robust, well-known Python ecosystem |
| Geo processing | GeoPandas + Shapely + Fiona | Industry standard, easy to work with |
| Rendering | Mapnik Python bindings or Cairo/SVG | Mapnik gives proper vector cartography; SVG/Cairo as fallback |
| PDF output | reportlab / svglib / Cairo | Direct vector PDF generation |
| Font metrics | fonttools / FreeType | Accurate printed-size font checks |
| Preview / geofence UI | Leaflet or MapLibre | Simple web map for drawing the geofence |
| Storage | Local filesystem or MinIO | No need for cloud in MVP |
| Job state / audit | SQLite + JSONL | Simple, portable |

---

## 8. Risks and mitigation

| Risk | Mitigation |
|---|---|
| OSM completeness gaps | Corrections file + documented process |
| Detail/legibility conflict | Explicit minimum-font check + user warning + offer larger paper/inset |
| Reference style ambiguity | Initial style manually measured from MCY and versioned; client approves before mass use |
| Prototype fragility | Modular architecture, unit tests per feature class, test on multiple areas |
| Commercial print failure | Output vector PDF; preflight checks fonts/colours/page boxes |
| Over-reliance on AI | [REDACTED] only coordinates; all cartography is deterministic code + rules |

---

## 9. Phased build plan (revised)

### Phase 0 — Scaffold + data (Week 1)
- Set up FastAPI/Celery project, local artifact store, SQLite job state.
- Implement OSM fetch/caching module for roads, water, parks, boundaries.
- Add corrections-file loader.
- Write first tests: fetch, cache, apply corrections.

### Phase 1 — Basic rendering (Weeks 2–3)
- Build YAML style engine from MCY-derived values.
- Render a simple vector PDF for one test area with roads, water, parks.
- Test on Noosa / Bribie / Maroochydore.

### Phase 2 — Geofence + legibility calculator (Weeks 4–5)
- Add geofence input to job.
- Calculate map scale for chosen paper size/orientation.
- Implement minimum-font-size warning and suggestions (larger paper / smaller area / inset).
- Tests: known bad extents trigger warnings; good extents pass.

### Phase 3 — Labels + furniture (Weeks 6–7)
- Label placement and collision detection.
- Repeated labels along long roads.
- Add title, scale bar, north arrow, legend, grid, attribution.
- QA report of dropped/overlapping labels.

### Phase 4 — Multi-format templates + proof flow (Weeks 8–9)
- A3/A4/A5 landscape/portrait templates.
- Inset/back-page generation when needed.
- Proof PDF + QA report output; review/approve flow.

### Phase 5 — Hardening against MCY reference (Weeks 10–11)
- Compare output visually/metrically with MCY PDF.
- Tune style values until accepted as “good enough” (or decide different style is acceptable).
- Run on 3–5 areas; fix edge cases.

### Phase 6 — Packaging + runbook (Week 12)
- Docker packaging.
- Client corrections-file guide.
- Runbook for generating a new map area.
- Final reproducibility test.

---

## 10. Effort estimate (revised, street-maps-only scope)

### 10.1 Assumptions
- August works as lead architect + developer.
- Client provides MCY reference PDF and one or two other test areas.
- No advertising/QR layer in this MVP.
- Client reviews PDF proof and accepts/tweaks style within scope.

### 10.2 Calendar time

| Phase | Estimate | Cumulative |
|---|---|---|
| Phase 0 — Scaffold + data | 1 week | 1 week |
| Phase 1 — Basic rendering | 2 weeks | 3 weeks |
| Phase 2 — Geofence + legibility | 2 weeks | 5 weeks |
| Phase 3 — Labels + furniture | 2 weeks | 7 weeks |
| Phase 4 — Templates + proof flow | 2 weeks | 9 weeks |
| Phase 5 — MCY reference tuning | 2 weeks | 11 weeks |
| Phase 6 — Packaging + runbook | 1 week | 12 weeks |

**Revised total: approximately 12 weeks for a street-map-only MVP.**

### 10.3 Effort breakdown (August-hours)

| Activity | Hours |
|---|---|
| Architecture + PRD refinement | 20 |
| FastAPI/Celery scaffold + job API | 40 |
| OSM ingest / cache / corrections file | 35 |
| Style engine (MCY-derived YAML rules) | 50 |
| Cartographic rendering (roads/water/parks/boundaries) | 60 |
| Geofence + legibility calculator | 40 |
| Label placement + collision | 60 |
| Map furniture | 40 |
| Multi-format templates | 35 |
| Preflight QA + reports | 40 |
| Proof/review flow + UI | 35 |
| Reproducibility + audit bundle | 25 |
| MCY reference validation + tuning | 50 |
| Docker/runbook/documentation | 25 |
| Buffer (15%) | ~65 |
| **Total August-hours** | **~580 hours** |

### 10.4 Custom skills / plugin / memory work

- Custom skills (~24 hours): `maps4u-style-extractor`, `maps4u-legibility-rules`, `maps4u-qa-report`.
- [REDACTED] plugin for map-job endpoints (~15 hours).
- Checkpoint + Open Brain memory (~12 hours).
- Included in totals above.

---

## 11. Success criteria

- [ ] User can define a new area by geofence and paper size.
- [ ] System warns if minimum font legibility cannot be met and suggests alternatives.
- [ ] Output is a print-ready vector PDF with selectable text and map furniture.
- [ ] QA report lists dropped labels, overlaps, and legibility warnings.
- [ ] Corrections file can be edited by client and re-ingested.
- [ ] Output is visually consistent with MCY reference style or an explicitly approved alternative.
- [ ] Same job inputs regenerate the same output (deterministic, within logged non-determinism).
- [ ] System runs end-to-end on at least 3 representative areas.

---

## 12. Open questions remaining

1. Can we get the **MCY reference PDF** and exact paper size/orientation it was printed at?
2. Which **3–5 pilot areas** should we validate against first?
3. Do you want a **web-based geofence tool**, or is a lat/lon/bbox text input + map preview okay for MVP?
4. What is the **minimum printed font size** you accept? (suggest 1.5 mm as default)
5. Do you need **CMYK PDF/X output**, or RGB vector PDF that the printer can convert?
6. Would you prefer the system as a **local Docker service** on your laptop, or a hosted web service?
7. Are insets/back-of-map pages a must-have for the first version, or a nice-to-have?

---

*End of revised PRD.*
