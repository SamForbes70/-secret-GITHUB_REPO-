# MAPS4U End-to-End Development Plan

**Document ID:** MAPS4U-PLAN-001
**Version:** 1.0
**Status:** Authoritative implementation blueprint for the MAPS4U Street Map System MVP
**Project slug:** `maps4u-maps`

**Source inputs (read and incorporated in full):**

- `/a0/usr/workdir/maps4u-machine-prd-v2.md` — PRD v2 (363 lines)
- `/a0/usr/workdir/maps4u-august-project-input.md` — project input (220 lines)
- Active project instructions for `maps4u-maps`

**Authoritative deliverable:** `/a0/usr/workdir/maps4u-end-to-end-development-plan.md`

---

## 0. How to use this document

This plan is written so that a competent autonomous engineering agent can execute it **sequentially, top to bottom**, from an empty repository to a tested, deployed production application, without inventing architecture, sequence, or definitions of done.

**Reading order for the executing agent:**

1. Read §1–§5 once (product, architecture, stack, repo, data). Do not start coding until these are understood.
2. Follow §9 to stand up the environment.
3. Execute §10 phase by phase, task by task. Each task has objective / inputs / actions / outputs / dependencies / acceptance criteria / tests / completion conditions. Do not reorder tasks unless a dependency note explicitly permits it.
4. Honour the gates in §11 (what must pass before phase progression) and the checkpoint protocol in §17.
5. Use §6–§8 and §12–§16 as reference contracts while executing §10.

**Document conventions:**

- Requirement IDs: `FR-xx` functional, `NFR-xx` non-functional; MoSCoW priority (M/S/C/W).
- `A-x` assumption, `C-x` constraint, `D-x` dependency, `Q-x` open question, `PA-x` provisional answer the plan proceeds on until the client confirms otherwise.
- `ADR-x` architecture decision record (full ADRs in repo at `docs/adr/`).
- `F-xx` feature, `Px.Ty` task y in phase x, `Gx` phase gate, `Mx` milestone.
- All paths are Linux paths. All commands assume the dev environment of §9.
- `PROVISIONAL` marks anything depending on unconfirmed client input (§1.7).
- Out-of-scope guard: advertising, QR codes, M2G, DDD, Google Business Profile, self-service portal are **explicitly excluded**. If a task seems to require them, stop and re-read §1.8.

---

## 1. Product definition

### 1.1 Purpose

Maps4U has a 30-year-old printed street-map business whose maps are manually produced — slow and expensive for every new area. Earlier AI experiments failed because generic interactive maps suppress detail at broad extents, AI outputs were not inspectable or reproducible, and the detail-vs-legibility conflict was never explicitly resolved.

MAPS4U (the Street Map System) is a **deterministic, repeatable pipeline** that turns a user-drawn geofence plus a paper-size choice (A3/A4/A5, landscape/portrait) into a **reviewable, print-ready vector PDF street map** styled after the Maroochydore (MCY) reference map, with an explicit legibility guarantee, a QA report a non-technical reviewer can act on, and a full reproducibility bundle.

The business value: automate the most painful, manual, expensive part of creating a new map area. Advertising/QR/self-service layers may be added later without touching the cartographic core.

### 1.2 Target users and personas

| Persona | Description | Needs |
|---|---|---|
| **Operator (David)** | Maps4U production staff, non-developer, laptop | Draw a geofence, pick paper size, get warned early about legibility, receive proof PDF + plain-language QA report, apply local corrections, approve/reject |
| **Business owner (Sam Forbes)** | Approves style fidelity and commercial readiness | Output matches MCY look, reproducibility, no silent data loss |
| **Reviewer** | Non-technical staff checking proofs | Open PDF and QA report with no dev tools; clear approve/reject path |
| **Executing engineering agent** | Builds/runs the system (this plan's primary reader) | Unambiguous, ordered, verifiable tasks |

MVP is single-operator; multi-user is post-MVP (§1.8).

### 1.3 Primary use cases

- **UC-1 Create map job:** draw geofence on preview map, enter area name + edition, select paper/orientation, submit.
- **UC-2 Viability check:** system computes implied print scale and minimum printed font size; warns and offers larger paper / smaller area / reduced density / inset-split.
- **UC-3 Render proof:** fetch/caches OSM data, applies style, resolves labels, composes furniture, renders vector PDF proof + QA report.
- **UC-4 Review:** reviewer opens proof + QA report; approves or rejects with note.
- **UC-5 Local corrections:** operator edits a YAML corrections file locally; system re-ingests and re-renders, recording the file hash.
- **UC-6 Reproduce:** any historical job regenerates from its bundle with identical output within the logged non-determinism policy.
- **UC-7 Configure style:** versioned style spec (YAML) updated from MCY measurements; client approves a style version before mass use.
- **UC-8 Operate locally:** whole system runs as a local Docker service on a laptop (PROVISIONAL PA-6).

### 1.4 Functional requirements (MVP unless noted)

| ID | Requirement | MoSCoW | Source |
|---|---|---|---|
| FR-01 | Accept job: area name, geofence polygon (GeoJSON), paper size (A3/A4/A5), orientation, edition info, style version | M | PRD §3.1 |
| FR-02 | Web preview map where operator draws/edits the geofence (Leaflet + draw control) | M | PRD §5.3, PA-3 |
| FR-03 | Compute implied print scale from geofence bounds + paper template (margins, furniture reserve) | M | PRD §3, §5.3 |
| FR-04 | Compute minimum printed font size at that scale; warn when below configurable threshold (default 1.5 mm) with four remediation options | M | PRD §3.4, §5.3 |
| FR-05 | Fetch OSM data via Overpass/osmnx: roads (motorway→service/path), waterways, parks/reserves, suburb boundaries, coastline, named places/landmarks | M | PRD §3.2, §6.2 |
| FR-06 | Cache fetched data keyed by bbox + source tag + timestamp; record provenance + ODbL attribution | M | PRD §6.2 |
| FR-07 | Corrections file (YAML/GeoJSON) loader: rename/add/remove features; record hash; auto-reapply per area | M | PRD §3.9, §5.4 |
| FR-08 | Version-controlled YAML/JSON style engine (colours, line weights, road hierarchy, water/park fills, label rules, legend keys); no cartographic constants in code | M | PRD §3.3, §6.3 |
| FR-09 | Scale-dependent feature selection (drop/simplify minor classes at small scales per style config) | M | PRD §3.4 |
| FR-10 | Label engine: label every street that can stay legible; repeated labels along long roads; priority ordering; collision detection; multi-position candidates; edge-safe | M | PRD §3.4, §6.4 |
| FR-11 | Dropped-label reporting with reason (collision, scale, priority) | M | PRD §6.4, §6.6 |
| FR-12 | Map furniture: title block, metric scale bar, north arrow, legend keyed to style, grid/street-index grid, ODbL copyright, date/edition note | M | PRD §3.6, §6.5 |
| FR-13 | Vector PDF proof, selectable text, sharp linework; A3/A4/A5 × landscape/portrait templates | M | PRD §3.7, §6.3 |
| FR-14 | Preflight QA report (human-readable): min-font violations, overlaps, clipped labels, dropped streets + reasons, vector/raster check, missing feature classes | M | PRD §3.8, §6.6 |
| FR-15 | Review flow: approve → lock bundle → final PDF; reject → job edit | M | PRD §3.8, §6.7 |
| FR-16 | Reproducibility bundle: job JSON, OSM snapshot, style version, renderer version, corrections hash, output checksum | M | PRD §3.10 |
| FR-17 | Async job execution with visible status (queued→…→proof_ready→finalized) | M | PRD §5.1 |
| FR-18 | Inset/back-page generation when one sheet cannot be complete and legible | S (Phase 4, feature-flagged) | PRD §3.5, Q-7 |
| FR-19 | Multi-position label candidates with curve-following street-name placement | M | PRD §5.1 |
| FR-20 | Style/version listing + client approval marker | S | PRD §8 |
| FR-21 | Audit trail: every job event + decision persisted (SQLite + JSONL) | M | PRD §5.1 |
| FR-22 | Health/readiness endpoints | M | §13 |
| FR-23 | Imperial scale bar option | C | PRD §6.5 |
| FR-24 | Multi-page atlas beyond front + inset/back | W (post-MVP) | PRD §4 |

### 1.5 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | **Determinism:** same inputs → same output: byte-identical PDFs, or raster-identical at 300 dpi (zero differing pixels); residual non-determinism logged in bundle | Every phase gate |
| NFR-02 | **Legibility guarantee:** never silently produce text below threshold (default 1.5 mm, configurable); fits or explicitly warns | 100% of jobs |
| NFR-03 | **Performance:** cached A4 re-render ≤ 90 s on 2020-era laptop; cold render incl. Overpass ≤ 5 min for ≤ 25 km² | Local Docker |
| NFR-04 | **Portability:** runs via `docker compose up` on Ubuntu 22.04+ / macOS Docker Desktop, no host Python | Client laptop |
| NFR-05 | **Auditability:** every job has JSONL event log + bundle; historical output regenerable | 100% of jobs |
| NFR-06 | **Offline-after-fetch:** once cached, pipeline runs with no network | Per area |
| NFR-07 | **Usability:** reviewer needs no dev tools; operator needs no CLI for UC-1..UC-5 | UAT §11.7 |
| NFR-08 | **Security baseline:** no secrets in repo; dependency scanning in CI; input validation on uploads/geometries | §8 |
| NFR-09 | **Licensing:** ODbL attribution on every sheet; fonts embedded under licence (OFL) | Legal |
| NFR-10 | **Capacity:** single operator, queue depth ≥ 5; areas up to ~100 km² per sheet | MVP |
| NFR-11 | **Coverage:** ≥ 85% line coverage on `core`, `geo`, `render`, `labels`, `qa` | CI gate |
| NFR-12 | **Data sovereignty:** all data on operator machine; only egress Overpass + preview tiles | §5.9 |

### 1.6 Assumptions, constraints, dependencies

**Assumptions (A):**

- A-1: MCY reference PDF will be supplied, with printed paper size/orientation.
- A-2: Pilot areas: Noosa, Bribie Island, Sandstone Point + up to 2 more (Sunshine Coast / Moreton Bay, QLD).
- A-3: OSM completeness in pilot areas adequate; gaps handled via corrections file.
- A-4: Operator machine runs Docker, ≥ 8 GB RAM.
- A-5: Style v1 measured manually from MCY PDF (no AI extraction).
- A-6: English labels, LTR text; no complex-script shaping for v1 fonts.

**Constraints (C):**

- C-1: MVP scope lock: no advertising, QR, M2G, DDD, GBP, self-service portal.
- C-2: Cartographic rules live in versioned config, not code.
- C-3: TDD: every cartographic rule gets a failing test first.
- C-4: Python 3.12+ runtime; stack per §3.
- C-5: Overpass fair-use: max 2 concurrent (configured 1), retry with backoff, 5 s gaps.
- C-6: Dev container has no Docker CLI and no local Redis (verified); Docker packaging validated in CI and on the client laptop.

**Dependencies (D):**

- D-1: Overpass API availability (public or self-hosted; §7.3).
- D-2: OSM data + ODbL compliance.
- D-3: Preview basemap tiles within provider usage policy.
- D-4: Client review cycles for style acceptance (Phase 5) — schedule risk if slow.
- D-5: Open-licence fonts (Noto Sans / DejaVu) unless client supplies licensed fonts.

### 1.7 Unresolved questions and provisional answers

The plan proceeds on these provisional answers (PA), flagged `PROVISIONAL`, consolidated in Appendix H, surfaced to the client at the first checkpoint review; record resolutions in Open Brain.

| # | Open question | Provisional answer |
|---|---|---|
| Q-1 | MCY reference PDF + its printed paper size/orientation? | PA-1: Required before Phase 1 style measurement and Phase 5 tuning; block P1 style tasks until received. |
| Q-2 | Which 3–5 pilot areas? | PA-2: Noosa, Bribie Island, Sandstone Point + Maroochydore (reference) + one inland rural area chosen in Phase 5. |
| Q-3 | Web geofence tool or bbox text input? | PA-3: Lightweight web tool (Leaflet + draw); core user story requires drawing; no user accounts. |
| Q-4 | Minimum printed font size? | PA-4: 1.5 mm default, configurable via `MAPS4U_MIN_FONT_MM` + style spec. |
| Q-5 | CMYK PDF/X required or RGB acceptable? | PA-5: RGB vector PDF with CMYK-safe palette; PDF/X evaluated in Phase 6 (Ghostscript path documented). |
| Q-6 | Local Docker service or hosted web service? | PA-6: Local Docker service on operator laptop; hosted is post-MVP. |
| Q-7 | Insets must-have or nice-to-have? | PA-7: Phase 4 behind feature flag `MAPS4U_INSETS_ENABLED` (default on); de-scopable without affecting earlier phases. |

### 1.8 MVP vs later enhancements

**MVP (this plan):** UC-1..UC-8, FR-01..FR-22 (+FR-18 flagged), street maps only, single operator, local Docker.

**Explicitly out of MVP (do not build; note as future projects if they arise):**

- Advertising layout, ad slots, advertiser artwork, QR codes / managed redirects.
- M2G, Google Business Profile, DDD integrations.
- Online customer self-service portal.
- AI-driven style extraction from the MCY PDF (v1 manually measured).
- Multi-page atlases beyond front map + optional inset/back page.

**Later (roadmap context only):** multi-user roles, hosted SaaS, ad/QR layer, automated style extraction, atlas generation, PostGIS migration if multi-operator concurrency demands it.

### 1.9 Design-baseline reconciliation (authoritative, Sept 2026)

The design proposal `dw input to sam's ai map plan with notes fm our call 21.9.26.docx` (Sam Forbes, 9 Sept 2026, with David's note 11 Aug 2026) **supersedes the July 2026 PRD v2 where they conflict**. Key deltas now binding on this plan:

1. **Renderer:** Cairo/SVG is the first implementation, with an early comparison **spike against Mapnik** (§2.4 revised). ReportLab remains a documented fallback if the spike fails. ADR-1 revised accordingly.
2. **Storage:** Production design assumes **PostgreSQL/PostGIS + S3-compatible object storage**; lightweight local substitutes (SQLite + GeoPackage + filesystem) are permitted for development and the pilot. ADR-2 revised to a dual-profile decision with a migration path (§5.10).
3. **Determinism standard (softened):** Acceptance target is **reproducible content, geometry, layout, structure and recorded hashes under the pinned environment** — golden tests on canonical layouts and PDF structure, not raw byte equality. Byte-identity applies only when PDF metadata/object ordering is normalised. NFR-01/ADR-4 revised.
4. **Records model expanded:** Organisation/membership, **immutable map projects and geofence revisions**, **render specification** (frozen inputs), OSM extract with raw-bytes provenance, artefact, QA finding, **review decision**, append-only audit event (§5.11).
5. **Outputs:** every governed render produces **proof PDF + raster thumbnail + QA report + manifest as one output set**; a job cannot be shown as successful if any is missing.
6. **New rule:** **no unseeded randomness** anywhere in label placement or rendering; seeded determinism only.
7. **Legibility:** 1.5 mm minimum is provisional **for the pilot only, subject to owner approval**, confirmed via printed samples.
8. **Delivery:** 8 gated stages — Stage 0 Reconcile/approve … Stage 7 Production hardening (OIDC identity, roles, AWS option, load testing) as a **separate post-pilot decision** (§15).
9. **Governance:** David approves scope/reference rights/print rules/pilot areas/style direction/pilot acceptance; Sam owns design/build/gates; printer validates physical samples. **David's note (11 Aug 2026): this is a secondary 'filler' project, not urgent — the build must therefore be phase-gated, resumable, and never block on idle periods.** A meeting is required to supply open info (MCY source files, pilot areas, print standard).
10. **Owner decision ticks observed** in the returned document (ambiguous scan): MCY reference & rights ✓, minimum printed type ✓, print standard ✓ — treat as **indicative, confirm at Stage 0**; pilot areas, insets, hosting, identity, retention, cartographic reviewer remain open.

Where this reconciliation and older parts of this document conflict, **this section wins**.
---

## 2. System architecture

### 2.1 Architecture overview

A containerised, layered **pipeline-orchestrator architecture** with two deployment profiles: **pilot** (single-node local Docker: FastAPI + Celery/Redis + SQLite/GeoPackage + filesystem artifacts — per David's approved local-hosting position) and **production** (PostgreSQL/PostGIS + S3-compatible object storage + OIDC identity, per the Sept 2026 design proposal Stage 7, a separate owner decision).

```
┌──────────────────────────── Pilot host: Docker Compose ────────────────────────────┐
│  Operator browser (Leaflet UI, served by FastAPI)                                  │
│      │ draw geofence / pick paper / review proof                                   │
│      ▼                                                                             │
│  FastAPI (api) ── validate, freeze render spec ──▶ Celery/Redis ──▶ Worker pipeline │
│      │                                               stages: validate→assess→       │
│      │                                               acquire→transform→style→        │
│      │                                               label→compose→render→verify     │
│      ▼                                               │                              │
│  SQLite (projects, revisions, jobs, findings,        │                              │
│          decisions, audit) + artifacts dir ◀─────────┘  proof.pdf + thumb.png +     │
│  GeoPackage/OSM cache                                        qa-report + manifest │
└───────────────────────────────────────────────────────────────────────────────────┘
     external: Overpass API (bounded queries, cached) · OSM tiles (preview only)
```

Production profile (Stage 7, post-pilot decision): same code; PostgreSQL/PostGIS as system of record; S3-compatible artefact storage; OIDC authn; roles operator/cartographer/reviewer/admin/support; private networks; managed AWS hosting.

### 2.2 Components and responsibilities

| # | Component | Responsibility | Module |
|---|---|---|---|
| 1 | Operator web app | Project setup, geofence drawing/edit, scale feedback, job progress, proof review + approval | `ui/static` (Leaflet + vanilla JS for pilot; React/Next.js permitted upgrade at Stage 7) |
| 2 | Application API | Validate requests, permissions, freeze render specifications, expose job state | `src/maps4u/api` |
| 3 | Job orchestration | Async stages with safe retry + checkpoints (Celery/Redis) | `src/maps4u/worker` |
| 4 | Geospatial processing | Geometry validation, projection selection, clip, classify, generalise by scale band | `src/maps4u/geo` |
| 5 | Cartography & labels | Style rules → ordered vector primitives; label candidates, text metrics, collision resolution | `src/maps4u/render`, `src/maps4u/labels` |
| 6 | Vector rendering | Vector paths, embedded text, composed PDF pages + raster thumbnail | `src/maps4u/render/cairo_canvas.py` (+ spike modules) |
| 7 | Quality engine | Legibility, coverage, placement, PDF structure, fonts, attribution, hash agreement | `src/maps4u/qa` |
| 8 | System of record | Projects, immutable specs, jobs, findings, decisions, audit events | `src/maps4u/core` (SQLite pilot / PostGIS prod) |
| 9 | Artefact storage | Extracts, proofs, QA reports, thumbnails, manifests | filesystem pilot / S3-compatible prod |
| 10 | Review & approval | Approve/reject immutable proof with comment; lock artefact record | `src/maps4u/api/routes_jobs.py` |

### 2.3 End-to-end processing (10 stages, each with recorded evidence)

| Stage | What happens | Evidence recorded |
|---|---|---|
| 1 Validate | Project, geofence, paper, config | Canonical geometry + input hashes |
| 2 Assess | Working projection, scale, legibility rules | Scale assessment + warnings |
| 3 Acquire | Cached extract or bounded Overpass request | Raw bytes, query, source time, checksum |
| 4 Transform | Reproject, clip, repair, simplify by scale band | Canonical feature set + provenance |
| 5 Style | Features → ordered vector primitives | Style ID + version + config hash |
| 6 Label | Measure text, fixed-order candidates, collisions | Accepted + rejected label candidates |
| 7 Compose | Page frame, furniture, attribution, proof marks | Frozen layout specification |
| 8 Render | Vector PDF + preview thumbnail | PDF, thumbnail, artefact hashes |
| 9 Verify | Cartographic + structural QA from frozen job | JSON + human-readable QA reports |
| 10 Review | Approve/reject immutable proof | Reviewer, decision, comment, timestamp |

A job is only successful when **proof + thumbnail + QA report + manifest all exist**. A material change to geofence/style/paper/source/override creates a **new render job** and requires a new decision.

### 2.4 Rendering architecture — ADR-1 (Cairo/SVG first, Mapnik spike)

**Decision (per Sept 2026 proposal):** all drawing goes through an internal **Canvas protocol**; the v1 implementation is **Cairo (Pycairo) → SVG/PDF**; an early spike must compare output quality, label control and determinism against **Mapnik** before Phase 1 style work begins.

**Binding spike criteria (P1.T1):** (a) vector paths + embedded text on A3/A4/A5; (b) OFL font embedding + exact metrics; (c) reproducible output under the §2.6 determinism standard; (d) label placement fully instrumentable (every candidate + accept/reject reason retrievable). Cairo wins ties (install simplicity, protocol control). ReportLab documented as third fallback; the choice is recorded in `docs/adr/0001`.

### 2.5 Architecture decision register (ADRs in repo `docs/adr/`)

| ADR | Decision | Rationale | Revisit trigger |
|---|---|---|---|
| ADR-1 | Canvas protocol; Cairo/SVG v1, Mapnik spike, ReportLab fallback | Sept 2026 proposal; install risk; label instrumentation; determinism | Spike failure → fallback |
| ADR-2 | **Dual-profile storage:** SQLite + GeoPackage + filesystem (pilot), PostgreSQL/PostGIS + S3 (production, Stage 7) | Proposal permits lightweight local substitutes; zero DB admin for pilot; production-grade for hosted | Stage 7 owner decision |
| ADR-3 | Static Leaflet UI for pilot; React/Next.js + MapLibre upgrade deferred | 3 interactive screens; no build chain on operator laptop; proposal allows either | Stage 7 / portal requirement |
| ADR-4 | **Content-level determinism:** reproducible content/geometry/layout/structure + hashes under pinned environment; byte-identity only with metadata normalisation | Sept 2026 proposal §13 | PDF backend change |
| ADR-5 | Public Overpass default, self-host/managed option if volumes grow | Fair-use at pilot scale; documented escape hatch | Throttling observed |
| ADR-6 | UTM (MGA zone 56 for pilots) working CRS; EPSG:4326 on disk | Metric print math; portable extracts | Cross-zone areas (split first) |
| ADR-7 | overpy + GeoPandas fetch core; osmnx dev convenience only | Deterministic queries, fixture recording | Graph ops needed (not in MVP) |
| ADR-8 | Immutable geofence revisions + frozen render specification | Proposal §8, §14: approval refers to exact inputs | — |
| ADR-9 | **Seeded randomness only**; no unseeded randomness in placement/render | Proposal §10 | — |

### 2.6 Failure isolation

- API never blocks on rendering (Celery async, safe retry, stage checkpoints).
- Worker crash → job auto-requeued from last checkpoint; stages idempotent.
- Overpass outage → bounded retries then `E_OVERPASS_UNAVAILABLE` with actionable message; cache unaffected.
- Corrupt GeoPackage → quarantine + refetch, logged.
- Preview tiles offline → gray grid; drawing and pipeline unaffected.
- Reviewer cannot approve a job missing any governed output (enforced server-side).

---

## 3. Technology stack

### 3.1 Stack (pin exact versions in `pyproject.toml`; floors shown)

| Concern | Choice | Floor | Why |
|---|---|---|---|
| Language | Python | 3.12 | C-4; geospatial wheel availability |
| Web/API | FastAPI + Uvicorn | 0.111 / 0.30 | Typed async API, OpenAPI docs; proposal §6 |
| Jobs | Celery + Redis | 5.3 / 7.2 | Async stages, retry, checkpoints |
| Geo core | GeoPandas, Shapely, pyogrio | 0.14 / 2.0 / 0.7 | Proposal §6 geospatial processing |
| OSM fetch | overpy (fixture-friendly) | 0.7 | Deterministic bounded queries, recorded fixtures |
| Rendering (v1) | **Pycairo → PDF/SVG** | 1.26 | ADR-1; proposal §6 |
| Spike comparison | python-mapnik | best-effort wheel | ADR-1 spike only; not a hard dependency |
| Fallback | ReportLab | 4.2 | ADR-1 third option |
| Text metrics | **Pango (via PangoCairo)** + fonttools | current | Proposal §6 typography; FreeType metrics fallback |
| PDF QA | **pikepdf** (qpdf), pypdf, pdfplumber | 8 / 4 / 0.11 | Proposal §6 structural checks |
| Thumbnails | PyMuPDF + Pillow | 1.24 / 10 | Raster preview generation, never the proof |
| Config | PyYAML + pydantic-settings | 6 / 2.8 | Versioned style/config engine (C-2) |
| Record store | SQLite (pilot) → PostgreSQL/PostGIS (prod) | 16 / 16-PostGIS | ADR-2 |
| Artefacts | filesystem (pilot) → S3-compatible (prod) | — | ADR-2 |
| Identity (Stage 7) | OIDC (provider TBD by owner) | — | Proposal §15 |
| Testing | pytest, pytest-cov, hypothesis | 8 / 5 / 6 | TDD (C-3), property tests |
| Quality gates | ruff, mypy | 0.5 / 1.10 | §4.2 |
| UI | Leaflet 1.9 + leaflet-draw 1.0, vanilla JS | vendored | ADR-3 pilot; React/Next at Stage 7 |
| Packaging | Docker multi-stage + compose v2 | python:3.12-slim | Same version in all envs |
| CI | GitHub Actions (or local hooks, no remote in MVP) | — | §12 |

**Not in pilot stack:** Mapnik (spike only), PostGIS/S3/OIDC (Stage 7), any analytics/telemetry (NFR-12), any AI component inside the production path (proposal: AI may assist analysis/transcription but makes **no unreviewed decisions**).

### 3.2 Alternatives considered

| Choice | Rejected alternative | Why |
|---|---|---|
| Cairo canvas protocol | Mapnik bindings | Wheel instability on py3.12+/ARM; label instrumentation; kept as spike per proposal |
| Cairo | matplotlib PDF | Chart-first; weaker page/text control |
| SQLite pilot store | PostGIS from day one | Pilot is single-operator local; ADR-2 dual profile defers cost |
| Leaflet static | Next.js SPA pilot | No build chain for 3 screens; upgrade path preserved |
| overpy | osmnx for fetch | Deterministic, recordable queries |
| UTM working CRS | Web Mercator | Mercator breaks metric print math |

### 3.3 Dependency policy

- Runtime deps pinned; lock committed; `pip-audit` in CI (NFR-08).
- Only overpy may call the network at runtime (§7.3).
- Fonts vendored in-repo with OFL licences; hashed into the style bundle (D-5).
- JS vendored into the image (no runtime CDN for app assets; preview tiles are network by design).
- Environment-specific extras (PostGIS/S3/OIDC) live behind an install extra `maps4u[production]` so the pilot image stays lean.

### 3.4 Fonts

- v1 family: Noto Sans (regular + bold) for street/place labels; DejaVu Sans as metric-stable test fallback.
- OFL-licensed; embedded (subset); licence text shipped; Pango/FreeType metrics computed **from the exact vendored TTFs**, never system fonts.
- Font substitution is a **QA failure** unless explicitly allowed by the style spec (proposal §10).
---

## 4. Repository and codebase design

### 4.1 Repository structure (authoritative)

Single repository at `/a0/usr/workdir/maps4u-street-map-system/` (per project input). Monorepo with one Python package plus the static UI:

```
maps4u-street-map-system/
├── pyproject.toml                  # build + deps + tool config (ruff, pytest, coverage)
├── .python-version                 # 3.12
├── README.md
├── Makefile                        # dev/test/lint/docker shortcuts
├── .env.example                    # every env var documented; copy to .env locally
├── .gitignore                      # .env, __pycache__, var/, .pytest_cache, dist/
├── .dockerignore
├── LICENSE                         # code licence (client to confirm; default proprietary)
├── docker/
│   ├── Dockerfile                  # multi-stage app+worker image
│   └── docker-compose.yml          # redis, app, worker (+ optional overpass profile)
├── deploy/
│   └── README-deploy.md            # client laptop deployment steps (generated in Phase 6)
├── config/
│   ├── settings.yaml               # non-secret operational defaults (paths, thresholds)
│   ├── paper_templates.yaml        # A3/A4/A5 × landscape/portrait templates (see §5.4)
│   └── logging.yaml                # structlog JSON config
├── styles/
│   └── mcy/
│       └── v1/
│           ├── style.yaml          # MCY-derived style spec (see §5.5)
│           └── fonts/              # OFL font files embedded at render time
├── schemas/
│   ├── job.schema.json             # JSON Schema for job definitions
│   ├── corrections.schema.json     # JSON Schema for corrections files
│   └── style.schema.json           # JSON Schema for style specs
├── src/
│   └── maps4u/
│       ├── __init__.py             # __version__ (single source; pyproject reads it)
│       ├── core/
│       │   ├── config.py           # pydantic-settings; env loading
│       │   ├── db.py               # sqlite connection, migrations runner
│       │   ├── models.py           # Job, JobEvent, Bundle dataclasses/pydantic models
│       │   ├── schemas.py          # request/response pydantic models (API boundary)
│       │   ├── state.py            # job state machine + legal transitions
│       │   ├── ids.py              # deterministic job_id/bundle_id helpers
│       │   ├── errors.py           # Maps4UError hierarchy + error codes
│       │   └── logging.py          # structlog setup
│       ├── geo/
│       │   ├── overpass.py         # Overpass client (retry/backoff, rate limit)
│       │   ├── fetch.py            # feature-class fetch orchestration
│       │   ├── cache.py            # GeoPackage snapshot store + reuse policy
│       │   ├── corrections.py      # corrections loader/validator/applier
│       │   ├── features.py         # FeatureSet container + validation
│       │   └── crs.py              # CRS selection (UTM zone calc), bbox helpers
│       ├── render/
│       │   ├── canvas.py           # Canvas protocol (drawing primitives)
│       │   ├── cairo_canvas.py     # Cairo implementation (ADR-1)
│       │   ├── style_engine.py     # style.yaml loading, validation, z-order plan
│       │   ├── scale.py            # scale + legibility calculator
│       │   ├── selection.py        # scale-dependent feature selection/simplification
│       │   ├── mapnik_probe.py     # ADR-1 spike only (not used in pipeline)
│       │   └── matplotlib_probe.py # fallback probe only
│       ├── labels/
│       │   ├── engine.py           # label orchestration
│       │   ├── candidates.py       # candidate generation (line-following, point)
│       │   ├── collision.py        # spatial index + collision detection
│       │   ├── priority.py         # class/importance priority + drop policy
│       │   └── metrics.py          # FreeType/fonttools text measurement
│       ├── layout/
│       │   ├── templates.py        # paper template model + loader
│       │   ├── furniture.py        # title/legend/scalebar/north/grid/attribution
│       │   └── composer.py         # page composition, inset page assembly
│       ├── qa/
│       │   ├── preflight.py        # QA checks orchestration
│       │   ├── pdf_checks.py       # vector/raster, fonts-embedded, page-box checks
│       │   └── report.py           # qa-report.md + qa-report.json renderers
│       ├── bundle/
│       │   ├── archive.py          # reproducibility bundle writer/reader
│       │   └── checksums.py        # sha256 helpers, determinism verifier
│       ├── api/
│       │   ├── main.py             # FastAPI app factory, router mounting, error handlers
│       │   ├── deps.py             # dependency injection (db, settings, storage)
│       │   ├── routes_jobs.py      # job CRUD + status + proof/qa/bundle download
│       │   ├── routes_viability.py # POST /api/viability
│       │   ├── routes_styles.py    # style listing + approval marker
│       │   ├── routes_system.py    # /healthz /readyz /api/meta
│       │   └── ui.py               # static UI serving + embedded assets
│       └── worker/
│           ├── celery_app.py       # celery factory + config
│           ├── tasks.py            # run_job pipeline task (per-stage substeps)
│           └── pipeline.py         # stage orchestration (fetch→style→select→label→compose→render→qa)
├── ui/
│   └── static/
│       ├── index.html              # single-page operator UI
│       ├── app.js                  # Leaflet map, draw control, job wizard, polling
│       └── styles.css
├── tests/
│   ├── conftest.py                 # fixtures: tmp dirs, test db, sample geometries
│   ├── fixtures/
│   │   ├── geofences/              # tiny bbox GeoJSON (Noosa, MCY, synthetic)
│   │   ├── overpass/               # recorded Overpass JSON responses (small)
│   │   └── styles/                 # minimal valid style.yaml for tests
│   ├── unit/                       # mirrors src package layout
│   ├── integration/                # db + cache + pipeline stages with fixtures
│   ├── api/                        # FastAPI TestClient route tests
│   └── e2e/                        # golden-map tests (deterministic end-to-end)
├── scripts/
│   ├── measure_style.py            # MCY measurement helper (semi-manual; Phase 1)
│   ├── verify_determinism.py       # run bundle twice; byte/raster compare
│   ├── export_pdfx.sh              # Ghostscript PDF/X conversion (Phase 6, PROVISIONAL)
│   └── new_area_runbook.sh         # end-to-end CLI walk-through for a new area
└── docs/
    ├── prd-v2.md                   # copy of the PRD for repo reference
    ├── architecture.md             # §2 of this plan, condensed
    ├── runbook.md                  # operator runbook (Phase 6)
    ├── corrections-guide.md        # client corrections-file guide (Phase 6)
    ├── api.md                      # API reference (generated from OpenAPI + notes)
    ├── testing.md                  # how to run tests, coverage policy
    ├── threat-model.md             # §8.8 condensed (Phase 0/6)
    ├── qa-acceptance.md            # UAT scripts + sign-off log (Phase 5/6)
    └── adr/
        ├── 0001-renderer-choice.md
        ├── 0002-geopackage-not-postgis.md
        ├── 0003-static-ui-not-spa-framework.md
        ├── 0004-deterministic-pdf-policy.md
        └── 0005-overpass-endpoint-policy.md
```

### 4.2 Naming and coding conventions

- **Python:** PEP 8 via `ruff` (line length 100); type hints on all public functions; `mypy --strict` on `core`, `geo`, `qa` packages (relaxed for `render` if backend typing is noisy).
- **Modules:** snake_case; packages singular (`label` → `labels` is the deliberate exception to mirror the domain); classes PascalCase; functions/vars snake_case; constants UPPER_SNAKE.
- **IDs:** `job_id` = slugified `{area_name}-{yyyymm}-{edition}` (e.g. `maroochydore-2026-07-ed1`), unique-constrained; `bundle_id` = `{job_id}-{sha256(job_json)[:8]}`.
- **Files:** artifacts named `{job_id}/proof.pdf`, `{job_id}/qa-report.md`, `{job_id}/final.pdf`, bundle dir `{job_id}/bundle/`; no spaces in any path.
- **Config:** all cartographic constants in `styles/*/style.yaml` + `config/paper_templates.yaml`; **zero cartographic magic numbers in Python** (enforced by review checklist; ruff custom rule optional).
- **Tests:** `test_{unit}.py`; one behavior per test; golden files under `tests/e2e/golden/` (git-lfs not required; PDFs are small vector files).
- **Commits/branches:** trunk-based; `main` always green; short-lived feature branches `phase{N}-{slug}`; conventional commits (`feat:`, `fix:`, `test:`, `docs:`).
- **Errors:** `Maps4UError(code, message, details)` with stable codes (`E_GEO_TOO_LARGE`, `E_STYLE_INVALID`, `E_OVERPASS_UNAVAILABLE`, …) surfaced to UI and QA report.

### 4.3 Environment variables (complete set)

| Variable | Default | Purpose |
|---|---|---|
| `MAPS4U_DATA_DIR` | `./var` | Root for artifacts, db, cache (docker: `/data` volume) |
| `MAPS4U_DB_PATH` | `${MAPS4U_DATA_DIR}/maps4u.sqlite3` | SQLite state db |
| `MAPS4U_ARTIFACT_DIR` | `${MAPS4U_DATA_DIR}/jobs` | Job artifacts + bundles |
| `MAPS4U_CACHE_DIR` | `${MAPS4U_DATA_DIR}/osm_cache` | GeoPackage snapshots |
| `MAPS4U_STYLE_DIR` | `./styles` | Style specs |
| `MAPS4U_DEFAULT_STYLE` | `mcy/v1` | Default style ref |
| `MAPS4U_MIN_FONT_MM` | `1.5` | Legibility threshold (PA-4) |
| `MAPS4U_OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | Overpass endpoint (ADR-5) |
| `MAPS4U_OVERPASS_MAX_CONCURRENCY` | `1` | Fair-use compliance (C-5) |
| `MAPS4U_TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Preview basemap (D-3) |
| `MAPS4U_CACHE_MAX_AGE_DAYS` | `0` (0 = reuse any local snapshot for determinism) | Cache policy (ADR-2) |
| `MAPS4U_INSETS_ENABLED` | `true` | FR-18 feature flag (PA-7) |
| `MAPS4U_OPERATOR_TOKEN` | empty (unset → auth off, local mode) | Auth toggle (§8.1) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/backend |
| `MAPS4U_RENDER_DPI` | `300` | Raster ops resolution (grid masks, QA raster compare) |
| `MAPS4U_LOG_LEVEL` | `INFO` | structlog level |
| `MAPS4U_ENV` | `dev` | `dev` / `test` / `staging` / `prod` profile switch |

No other env vars may be introduced without adding them to this table and `.env.example`.

---

## 5. Data architecture

### 5.1 Principal entities and relationships

```
Job 1───n JobEvent
Job 1───1 OsmSnapshot      (reuse allowed: OsmSnapshot 1───n Job)
Job 1───0..1 CorrectionsFile
Job 1───1 StyleVersion     (StyleVersion 1───n Job)
Job 1───0..1 Bundle        (created on approve; immutable)
StyleVersion 1───n StyleApproval
```

Entity definitions:

| Entity | Purpose | Key fields |
|---|---|---|
| `Job` | One map-production request and its lifecycle | job_id (PK), area_name, geofence_geojson, paper, orientation, style_ref, corrections_ref, status, scale_denominator, min_font_mm_result, created_at, updated_at |
| `JobEvent` | Append-only audit of transitions/actions | id, job_id (FK), ts, stage, event, payload_json |
| `OsmSnapshot` | A cached OSM extract for a bbox | snapshot_id (PK = sha256(bbox_norm + query_hash)), bbox, fetched_at, source_url, gpkg_path, osm_base_date (from Overpass meta), feature_counts_json, sha256 |
| `CorrectionsFile` | Client corrections + provenance | corrections_id (PK = sha256(content)), path, applied_at, sha256 |
| `StyleVersion` | A style spec release | style_ref (PK e.g. `mcy/v1`), path, sha256, approved_by, approved_at, notes |
| `Bundle` | Reproducibility archive | bundle_id (PK), job_id (FK), created_at, manifest_json, output_sha256 |
| `QaResult` | Latest QA outcome per job | job_id (FK), report_md_path, report_json_path, min_font_ok, overlaps, clipped, dropped_json |

### 5.2 SQLite schema (DDL — authoritative for Phase 0 migration `0001_init.sql`)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE jobs (
  job_id            TEXT PRIMARY KEY,
  area_name         TEXT NOT NULL,
  geofence_geojson  TEXT NOT NULL,          -- GeoJSON Polygon, EPSG:4326
  paper             TEXT NOT NULL CHECK (paper IN ('A3','A4','A5')),
  orientation       TEXT NOT NULL CHECK (orientation IN ('landscape','portrait')),
  edition           TEXT,
  style_ref         TEXT NOT NULL,
  corrections_ref   TEXT,
  status            TEXT NOT NULL,          -- state machine §6.1
  scale_denominator REAL,
  min_font_mm       REAL,
  error_code        TEXT,
  error_detail      TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE job_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id       TEXT NOT NULL REFERENCES jobs(job_id),
  ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  stage        TEXT NOT NULL,
  event        TEXT NOT NULL,
  payload_json TEXT
);
CREATE INDEX idx_job_events_job ON job_events(job_id);

CREATE TABLE osm_snapshots (
  snapshot_id   TEXT PRIMARY KEY,           -- sha256(norm_bbox + query_hash)
  bbox          TEXT NOT NULL,              -- "minlon,minlat,maxlon,maxlat" (EPSG:4326)
  fetched_at    TEXT NOT NULL,
  source_url    TEXT NOT NULL,
  gpkg_path     TEXT NOT NULL,
  osm_base_date TEXT,
  feature_counts_json TEXT,
  sha256        TEXT NOT NULL
);

CREATE TABLE corrections_files (
  corrections_id TEXT PRIMARY KEY,          -- sha256(content)
  path           TEXT NOT NULL,
  applied_at     TEXT,
  sha256         TEXT NOT NULL
);

CREATE TABLE style_versions (
  style_ref   TEXT PRIMARY KEY,             -- e.g. 'mcy/v1'
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  approved_by TEXT,
  approved_at TEXT,
  notes       TEXT
);

CREATE TABLE bundles (
  bundle_id     TEXT PRIMARY KEY,
  job_id        TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
  created_at    TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  output_sha256 TEXT NOT NULL
);

CREATE TABLE qa_results (
  job_id            TEXT PRIMARY KEY REFERENCES jobs(job_id),
  report_md_path    TEXT NOT NULL,
  report_json_path  TEXT NOT NULL,
  min_font_ok       INTEGER NOT NULL,
  overlaps          INTEGER NOT NULL,
  clipped           INTEGER NOT NULL,
  dropped_json      TEXT NOT NULL
);

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
```

**Migration strategy:** numbered SQL files `src/maps4u/core/migrations/0001_init.sql`, `0002_*.sql`, applied in order by `db.py` at startup inside a transaction; `schema_migrations` tracks applied versions. Rollback for MVP = restore from backup (§12.4); no down-migrations in MVP.

### 5.3 GeoPackage snapshot contract

One GeoPackage per snapshot at `${MAPS4U_CACHE_DIR}/{snapshot_id}.gpkg`, CRS = EPSG:4326 on disk (reprojected to working CRS in memory at render time). Layers (each with a `maps4u_class` column assigned by the fetch module):

| Layer | Geometry | Source OSM tags | Key columns |
|---|---|---|---|
| `roads` | LineString | highway=motorway..path/track | osm_id, name, ref, highway, oneway, surface, z_order_base |
| `water` | Polygon/MultiPolygon | natural=water, waterway=riverbank, landuse=reservoir | osm_id, name, water_type |
| `water_lines` | LineString | waterway=river/stream/canal | osm_id, name, waterway |
| `parks` | Polygon | leisure=park/nature_reserve, landuse=recreation_ground/forest | osm_id, name, park_type |
| `boundaries` | Polygon | boundary=administrative (admin_level 9/10 = suburb in AU) | osm_id, name, admin_level |
| `coastline` | LineString | natural=coastline | osm_id |
| `places` | Point | place=suburb/locality/town/hamlet, tourism=*, amenity=key POIs, natural=peak/cape | osm_id, name, place_type, importance |
| `landmarks` | Point | man_made=tower/lighthouse, historic=*, building=major civic (config list) | osm_id, name, landmark_type |

Each layer also carries `corrected` (0/1) and `correction_id` columns so re-runs show which features were modified by corrections.

### 5.4 Paper template contract (`config/paper_templates.yaml`)

```yaml
A3-landscape:
  page_mm: [420, 297]
  margins_mm: {top: 15, right: 15, bottom: 15, left: 15}
  furniture:
    title_block_mm: {x: 15, y: 12, w: 180, h: 18}
    legend_mm: {x: 330, y: 12, w: 75, h: 60}
    scale_bar_mm: {x: 15, y: 270, w: 80, h: 10}
    north_arrow_mm: {x: 390, y: 250, w: 15, h: 20}
    attribution_mm: {x: 100, y: 282, w: 220, h: 8}
  map_area_mm: null            # computed: page − margins − reserved furniture cells
  grid: {enabled: true, cell_mm: 40, labels: true}
# A3-portrait, A4-*, A5-* likewise (defined in Phase 0 task P0.T4)
```

`map_area_mm` is resolved at load: the largest axis-aligned rectangle inside margins excluding reserved furniture cells; the scale calculator consumes it (§6.3).

### 5.5 Style spec contract (`styles/mcy/v1/style.yaml`, excerpt)

```yaml
style_version: "1.0.0"
meta: {derived_from: "MCY-reference.pdf  suburb: {family: "Noto Sans", weight: bold, size_mm: 4.5, halo: {color: "#ffffff", width_mm: 0.6}}
  arterial: {family: "Noto Sans", weight: regular, size_mm: 2.6, spacing_mm: 0.1}
  local: {family: "Noto Sans", weight: regular, size_mm: 2.0}
label_rules:
  priority_order: [suburb, landmark, arterial, collector, local, service]
  candidate_order: [above, below, left, right]
  repeat_every_mm: 120
  max_repeats: 3
  min_font_mm: 1.5          # pilot-provisional per §1.9 item 7; confirmed via printed samples
  packing_factor: 1.8
layers:
  water:    {fill: "#aad3df", stroke: null, z: 1}
  parks:    {fill: "#c8e6c9", stroke: null, z: 2}
  roads:
    motorway:  {casing: {color: "#4a4a4a", width_mm: 1.6}, fill: {color: "#ffd54f", width_mm: 1.2}, z: 20}
    primary:   {casing: {color: "#4a4a4a", width_mm: 1.2}, fill: {color: "#ffffff", width_mm: 0.9}, z: 18}
    # ... measured values transcribed from MCY per §1.9; every unmeasurable value recorded for owner approval
  boundaries: {stroke: {color: "#888888", width_mm: 0.4, dash: [2, 1.5]}, z: 30}
legend: [...]               # auto-generated from classes actually present
scale_bands:                 # when features/labels appear, simplify, disappear (proposal §10)
  - {denominator_max: 8000,  classes: [all]}
  - {denominator_max: 20000, classes: [all_minus_service_and_track]}
  - {denominator_max: 50000, classes: [arterial_up, parks, water, suburb_labels_only]}
meta: {approved: false}      # style version approval is an owner decision (FR-20)
```

Style versions are **immutable once published**; any change creates a new semantic version and triggers visual-regression review (proposal §10).

### 5.6 Corrections schema (`schemas/corrections.schema.json`, binding)

```yaml
corrections:
  - feature: road
    osm_id: 123456789
    action: rename            # rename | add | remove | reclass
    name: "The Esplanade"
  - feature: place
    lat: -26.3992
    lon: 153.0894
    action: add
    name: "Sunshine Beach Headland"
    type: landmark
```

Rules: validated + versioned + attributable (author, date) + hash included in the job manifest; corrections never rewrite the cached source extract; corrections applied on a working copy; stale corrections (target feature changed upstream) flagged as QA warnings, never silently dropped.

### 5.7 Provenance + integrity chain (binding)

- Store the **raw Overpass response bytes** before parsing (proposal §9.2).
- Manifest links: job JSON hash → extract checksum + query + provider + source timestamp + licence → corrections hash → style version + config hash → font bundle hashes → renderer/app version + image digest → output PDF/thumbnail/QA hashes.
- ODbL attribution embedded on the sheet and in the manifest.

### 5.8 Ingestion, caching, retention, backup

- Fetch = bounded Overpass queries (5 class-groups, sequential, 5 s gaps, C-5) → raw bytes stored → parsed → validated (Shapely make_valid) → GeoPackage (§5.3) → counts recorded.
- Cache key `sha256(bbox + query_hash)`; `osm_base_date` from Overpass meta visible in UI/QA (source-date visibility per proposal §20).
- **Retention (owner decision pending):** retain every source extract for as long as an approved proof depends on it (proposal §9.2); rejected-proof retention TBD → Stage 0 question. MVP default: retain all; purge only manual.
- Backup: pilot = nightly `sqlite3 .backup` + rsync of artifacts dir to a second disk; **backup claims are accepted only after a successful restore exercise** (proposal §16) — restore drill scripted in Phase 6.

### 5.9 Privacy, security, sovereignty, regulatory

- All data on the operator machine in pilot; egress only Overpass + preview tiles (NFR-12).
- No personal data beyond system users; ODbL is the governing data licence (share-alike obligations documented in `docs/licensing.md` Phase 1).
- Production profile: encryption in transit + at rest, private DB/worker networks, short-lived signed artefact access, secrets outside source (§8).
- Australia-specific: nothing health/consumer-sensitive; standardPrivacy principles suffice for MVP.

### 5.10 Record model extension (Sept 2026 baseline, pilot schema)

Beyond §5.2, the pilot SQLite gains these tables (production moves them to PostGIS with identical column semantics):

```sql
CREATE TABLE map_projects (          -- proposal §14
  project_id TEXT PRIMARY KEY, area_name TEXT NOT NULL, created_at TEXT NOT NULL,
  reference TEXT, notes TEXT);
CREATE TABLE geofence_revisions (    -- immutable; each material edit = new revision
  revision_id TEXT PRIMARY KEY,      -- sha256(canonical geometry)
  project_id TEXT NOT NULL REFERENCES map_projects(project_id),
  geometry_json TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT,
  is_current INTEGER NOT NULL DEFAULT 0);
CREATE TABLE render_specifications ( -- freezes every input (ADR-8)
  spec_id TEXT PRIMARY KEY,          -- sha256(canon job spec)
  project_id TEXT NOT NULL, geofence_revision TEXT NOT NULL, paper TEXT NOT NULL,
  orientation TEXT NOT NULL, style_ref TEXT NOT NULL, corrections_id TEXT,
  spec_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE qa_findings (          -- rule, severity, message, evidence
  finding_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  rule TEXT NOT NULL, severity TEXT NOT NULL CHECK (severity IN ('blocker','warning','info')),
  message TEXT NOT NULL, evidence_json TEXT);
CREATE TABLE review_decisions (     -- approve/reject of the exact proof
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
  reviewer TEXT NOT NULL, decision TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
  comment TEXT, proof_sha256 TEXT NOT NULL, decided_at TEXT NOT NULL);
```

`jobs` gains `spec_id`, `project_id`, `geofence_revision`, `thumbnail_path` columns; a job missing proof/thumbnail/QA/manifest cannot transition to `proof_ready` (§2.3 rule).

### 5.11 Production-profile data architecture (Stage 7, decision-gated)

Same entities mapped to PostgreSQL/PostGIS (`geometry geography(Polygon,4326)` for geofences; extracts as GeoPackage blobs in S3 or PostGIS staging tables); artefacts in S3-compatible storage with short-lived signed URLs; organisation + membership + OIDC identities + role-based permissions (§8). No schema work starts before the Stage 7 owner decision.
---

## 6. Application functionality

### 6.1 Job lifecycle state machine (binding)

```
created ──▶ validating ──▶ queued ──▶ assessing ──▶ acquiring ──▶ transforming
 transforming ──▶ styling ──▶ labelling ──▶ composing ──▶ rendering ──▶ verifying
 verifying ──▶ proof_ready ──approve──▶ finalized (artefacts locked)
 proof_ready ──reject──▶ rejected (comment required)
 any stage ──error──▶ failed ──retry──▶ queued (from last checkpoint)
```

Rules:

- Transitions only via `core/state.py`; every transition appends a `job_events` row + JSONL audit line.
- `proof_ready` requires **all four governed outputs** (proof PDF, thumbnail, QA report, manifest) — server-enforced.
- `finalized` is immutable; any material input change (geofence revision, style, paper, corrections, source extract) creates a **new render job + new spec** and a new approval (ADR-8).
- `failed` carries `error_code` + safe human message surfaced in UI and QA (no stack traces to the operator).

### 6.2 Feature F-01 — Map project + geofence editor (FR-01, FR-02)

**Journey (UC-1):** sign in (pilot: local mode, no auth; Stage 7: OIDC) → create map project (area name, reference note) → search/pan preview map → draw Polygon/MultiPolygon → edit geometry (creates a **new immutable geofence revision**, old kept) → select paper + orientation → see live scale readout → proceed to viability.

**Backend:** validate geometry (GeoJSON Polygon/MultiPolygon, EPSG:4326, ≤ 200 vertices per ring, area ≤ 600 km² else `E_GEO_TOO_LARGE`), canonicalise (round coordinates to 7 dp, canonical JSON), hash → `geofence_revisions` row; `is_current` flag maintained.

**Edge cases:** self-intersection → reject with repair hint; antimeridian → `E_GEO_UNSUPPORTED` (MVP); ocean-only polygon allowed; MultiPolygon ≤ 3 parts (insets of the same area, not disjoint areas).

### 6.3 Feature F-02 — Scale + legibility assessment (FR-03, FR-04)

**Binding math:** working CRS = UTM zone of centroid (zone 56 pilots, ADR-6); `scale_denominator = max(width_m/(map_area_w_mm/1000), height_m/(map_area_h_mm/1000))` over the usable frame (margins + reserved furniture removed, per template). Style label sizes are fixed printed mm, so the legibility checks are: (a) every mandatory class size_mm ≥ configured minimum (1.5 mm pilot-provisional); (b) **density**: estimated named-feature labels vs `map_area_mm²/(avg_label_box_mm² × packing_factor)` from style config.

**On failure:** present the four owner-approved choices — larger sheet, smaller area, accept defined label-density reduction, approved inset/reverse-side layout. **Hard failures (geometry/schema) cannot be overridden.** Output: `{viable, scale_denominator, min_printed_mm, label_density_ratio, warnings[], choices[]}` — recorded as stage-2 evidence.

### 6.4 Feature F-03 — OSM acquisition + cache (FR-05, FR-06)

Bounded Overpass QL per class-group (roads; water+water_lines; parks; boundaries+coastline; places+landmarks), sequential, 5 s gaps, 120 s timeout, backoff 10/30/90 s → 3 attempts then `E_OVERPASS_UNAVAILABLE`. **Raw response bytes stored before parsing** (proposal §9.2). Parse → validate (make_valid) → GeoPackage (§5.3) → counts + `osm_base_date` recorded; UI shows source date. Cache hit on `sha256(bbox+query_hash)`.

### 6.5 Feature F-04 — Corrections (FR-07)

Schema §5.6. Validated, versioned, attributable; applied to a **working copy** (source extract never modified); corrections hash in manifest; stale targets (upstream changed) → QA warnings. Idempotent reapplication.

### 6.6 Feature F-05 — Transform + style engine (FR-08, FR-09)

`transforming`: reproject to working CRS, clip to geofence (+ clip buffer 2 % for context), repair permitted geometry, **simplify by scale band** (tolerance from style `scale_bands`); keep source geometry separate from render geometry. `styling`: style.yaml → validated → ordered vector primitives (fills → casings → fills → boundaries → grid) with style ID + config hash recorded as evidence.

### 6.7 Feature F-06 — Deterministic label engine (FR-10, FR-11, FR-19)

1. Candidates in **fixed order** (per class candidate_order; roads: 4 tangent-following positions at `label_spacing_mm` intervals; places: 8 halo positions).
2. Text measured with Pango/FreeType against **vendored TTFs** (exact embedded glyphs).
3. Stable priority sort (class weight, then name, then osm_id — no environmental order leaks).
4. Greedy placement against STRtree + forbidden zones (frame margin, furniture reserve); zero-intersection acceptance; every rejection reason recorded (`collision`, `clipped`, `too_short`, `scale_band`).
5. Repeats every `repeat_every_mm` up to `max_repeats`.
6. **Seeded randomness only** (ADR-9); default seed `0` recorded in the render spec.
7. Both accepted and rejected candidates are stage-6 evidence (proposal §7).

### 6.8 Feature F-07 — Compose + furniture (FR-12, FR-23)

Title block (area, edition, date), north indicator, metric scale bar (imperial optional), legend auto-keyed to classes actually present, grid with index labels, production reference + ODbL attribution, optional proof watermark. Frozen layout specification is stage-7 evidence.

### 6.9 Feature F-08 — Render + verify (FR-13, FR-14)

Cairo canvas → vector PDF (A3/A4/A5 × portrait/landscape; trim/bleed/margins/usable frame from template) + raster thumbnail (PyMuPDF). QA categories (proposal §12): input/geometry; cartographic (road-class coverage, empty-map detection, min font, collisions, clipping, dropped labels); PDF structure (page boxes, embedded fonts, vector paths, attribution, colour policy, no unexpected raster map layer — pikepdf); integrity (hash agreement across manifest); review readiness (no blocker findings; warnings visible + acknowledged). Outputs `qa-report.md` + `qa-report.json` (findings with rule/severity/message/evidence).

### 6.10 Feature F-09 — Review + approval (FR-15, FR-16, FR-17)

Proof viewer (browser PDF), thumbnail quick-view, QA evidence panel, approve/reject. Reject requires a comment. Approval locks the artefact record (`review_decisions` with `proof_sha256`). Any change → new render + new decision (ADR-8).

### 6.11 Feature F-10 — Inset / reverse-side (FR-18, flagged)

Optional per owner decision; behind `MAPS4U_INSETS_ENABLED`; when an approved area requires it: page 2 = zoomed inset of the densest tile + reverse-side furniture (full legend, street index if configured).

### 6.12 Feature dependency graph

```
F-01 project/geofence ─▶ F-02 assess ─▶ F-03 acquire ─▶ F-04 corrections
F-05 transform+style ─┐
                      ├─▶ F-06 labels ─▶ F-07 compose ─▶ F-08 render+verify
F-03/F-04 ────────────┘                                     │
                 F-10 inset (opt) ─────────────────────────▶│
                                    F-09 review+approve ◀───┘
```

---

## 7. API and integration design

### 7.1 Internal REST API (FastAPI, prefix `/api`)

| Method | Path | Request → Response | Errors |
|---|---|---|---|
| GET | `/api/meta` | → `{version, style_refs[], papers[], orientations[], thresholds}` | — |
| GET | `/healthz` · `/readyz` | liveness · readiness (db, redis, worker) | 503 |
| POST | `/api/projects` | `{area_name, reference?, notes?}` → `201 {project_id}` | 422 |
| GET | `/api/projects` | list | — |
| GET | `/api/projects/{id}` | project + current geofence revision + jobs | 404 |
| POST | `/api/projects/{id}/geofence` | GeoJSON geometry → `201 {revision_id, is_current}` (new immutable revision) | 422 |
| POST | `/api/viability` | `{geofence, paper, orientation}` → §6.3 contract | 422 |
| POST | `/api/jobs` | `{project_id, geofence_revision, paper, orientation, style_ref?, corrections_ref?}` → `201 {job_id, spec_id, status}` (render spec frozen here) | 409, 422 |
| GET | `/api/jobs?status=&limit=` | job list | — |
| GET | `/api/jobs/{job_id}` | job + stage + latest QA summary | 404 |
| GET | `/api/jobs/{job_id}/artifacts/{proof.pdf|thumb.png|qa-report.md|qa-report.json|manifest.json}` | governed outputs | 404/409 |
| POST | `/api/jobs/{job_id}/approve` | `{reviewer, note?}` → locks artefacts | 409 wrong state |
| POST | `/api/jobs/{job_id}/reject` | `{reviewer, comment}` (comment required) | 409, 422 |
| POST | `/api/jobs/{job_id}/retry` | re-queue from checkpoint | 409 |
| POST | `/api/jobs/{job_id}/corrections` | multipart YAML upload → validate + store + new job | 422 |
| GET | `/api/styles` · `POST /api/styles/{ref}/approve` | list · owner approval marker | 404 |

**Conventions:** JSON; error body `{error:{code,message,details}}` (problem-details compatible); `X-Request-ID` echo; geometry payloads schema-validated; OpenAPI at `/api/docs` is the API of record, exported to `docs/api.md` at Stage 6. Stage 7 adds OIDC bearer auth + organisation scoping + short-lived signed artefact URLs; pilot runs auth-free on localhost.

### 7.2 Internal module interfaces (binding signatures)

```python
# geo/acquire.py
def get_or_fetch(bbox: BBox, classes: list[str], settings: Settings) -> OsmExtract: ...
#   OsmExtract: raw_path, gpkg_path, query, source_ts, osm_base_date, sha256

# geo/corrections.py
def apply_corrections(features: FeatureSet, corrections_path: Path
                      ) -> tuple[FeatureSet, list[CorrectionWarning]]: ...

# render/assess.py
def assess(geofence: Polygon, template: PaperTemplate, style: StyleSpec) -> Assessment: ...

# render/style_engine.py
def style_plan(features: FeatureSet, style: StyleSpec, band: ScaleBand) -> DrawPlan: ...

# labels/engine.py
def place_labels(features: FeatureSet, plan: DrawPlan, frame: MapFrame,
                 style: StyleSpec, seed: int = 0) -> LabelResult: ...

# layout/composer.py
def compose(canvas: Canvas, plan: DrawPlan, labels: LabelResult,
            template: PaperTemplate, meta: JobMeta) -> LayoutSpec: ...

# render/cairo_canvas.py
class CairoCanvas(Canvas):  # ADR-1 v1 implementation
    def render_pdf(self, path: Path) -> None: ...

# qa/preflight.py
def run_qa(job: FrozenJob, pdf_path: Path, labels: LabelResult,
           features: FeatureSet, style: StyleSpec) -> QaReport: ...

# bundle/archive.py
def write_manifest(job: FrozenJob, extract: OsmExtract, style: StyleSpec) -> Manifest: ...
def reproduce(spec: RenderSpec, extract: OsmExtract, out_dir: Path) -> ReproResult: ...
```

### 7.3 External integrations

| Integration | Use | Policy |
|---|---|---|
| **Overpass API** | OSM extract | Bounded queries; concurrency 1 (C-5); 5 s gaps; 120 s timeout; retries 10/30/90 s; raw bytes stored; recorded fixtures for tests (no live calls in unit tests). Self-host/managed option if throttled (ADR-5) |
| **OSM tiles** | Preview only | Browser-side, attribution shown, within usage policy; PDF never uses tiles |
| **ODbL** | Data licence | Attribution on sheet + manifest; share-alike obligations in `docs/licensing.md` |
| **OFL fonts** | Embedded subsets | Vendored, hashed in manifest; substitution = QA failure unless allowed |
| **OIDC provider** (Stage 7) | Identity | Provider chosen by owner before production hardening |
| **Printer** | Print acceptance | Physical samples per format; requirements recorded in template config |

No other external calls; no telemetry/analytics (NFR-12); **AI components make no unreviewed decisions in the production path** (proposal §1).

### 7.4 Integration failure modes

| Failure | Behaviour |
|---|---|
| Overpass down/timeout | Retry ladder → `E_OVERPASS_UNAVAILABLE` + actionable message; cache intact |
| Throttled (429) | Backoff + queue deferral; surfaces owner suggestion (self-host option) |
| Tile server blocked | Gray grid; drawing/pipeline unaffected |
| Corrupt GeoPackage | Quarantine + refetch + audit event |
| Redis down | `/readyz` false; 503 on job create; compose restart policy |
| Disk full | Atomic stage writes (temp+rename); `E_STORAGE` |
| Missing governed output at verify | Job cannot reach `proof_ready` (server-enforced) |

### 7.5 Integration testing

- Recorded-fixture tests: Overpass JSON fixtures under `tests/fixtures/overpass/`; fixture mode via `MAPS4U_OVERPASS_URL=file://...`.
- Contract tests on Overpass meta fields + tile URL rendering.
- Compose smoke test: full offline end-to-end job (§11.3).
- `pytest -m live` manual pre-release check (1 km² bbox) against real Overpass.
---

## 8. Security

### 8.1 Authentication and authorisation

- **Pilot (local Docker):** auth-free on `127.0.0.1`; API binds localhost by default; a shared `MAPS4U_OPERATOR_TOKEN` (optional env, §4.3) gates mutating endpoints if the operator wants a second machine on a LAN. No user accounts, no passwords stored.
- **Production (Stage 7, decision-gated):** OIDC (provider chosen by owner); organisation-scoped access; short-lived signed artefact URLs; role-based permissions.

### 8.2 Roles and permissions (production design; pilot collapses all to operator)

| Role | Permissions |
|---|---|
| operator | create/edit projects + geofences, submit jobs, upload corrections, view outputs |
| cartographer | + style version authoring/approval workflow inputs |
| reviewer | view proofs + QA, approve/reject (comment required on reject) |
| administrator | users, retention, configuration |
| support | read-only job/artefact access for triage |

Approval actions are audit-logged with identity + timestamp (proposal §15).

### 8.3 Secrets management
- No secrets in the repo (CI-enforced gitleaks scan). `.env` gitignored; `.env.example` documents every var.
- Pilot: secrets limited to optional operator token + Overpass URL choice — both env-based.
- Production: secrets manager (AWS Secrets Manager or equivalent), injected as env at deploy; never in logs; token redaction middleware.

### 8.4 Application security
- Pydantic validation on every input (geometry, uploads, params); strict size caps (upload ≤ 1 MB corrections file; polygon caps §6.2).
- Safe error messages: operator sees codes + human text, never stack traces (proposal §5.6).
- Rate limits: 60 req/min default on API; queue depth cap 10; request-id tracing.
- Dependency/container/source/secret scanning in the release pipeline (`pip-audit`, trivy, gitleaks) (NFR-08, proposal §15).
- No AI component makes unreviewed decisions in the production path (binding).

### 8.5 Infrastructure security
- Pilot: compose network internal; only published API port on localhost; artifacts dir owned by app user; volumes not world-readable.
- Production: private DB/Redis/worker subnets; TLS everywhere; encryption at rest (DB + S3); immutable container digests; least-privilege IAM.

### 8.6 Audit logging
- Every state transition, approval, rejection, correction upload, style approval → append-only `job_events`/`audit_events` + JSONL. No tokens/secrets in logs. Approval records carry reviewer identity + proof checksum (ADR-8).

### 8.7 Vulnerability management
- Pinned deps + lockfile; `pip-audit` + trivy image scan in CI on every push; release blocked on high/critical; monthly refresh of pins; security runbook in `docs/runbook.md`.

### 8.8 Secure development practices
- TDD + code review checklist (§4.2); ruff + mypy gates; no `eval`/dynamic imports of user content; corrections YAML loaded with `yaml.safe_load`; threat-model note (`docs/threat-model.md`) updated at Stages 0 and 6.

---

## 9. Development environments

### 9.1 Environments

| Env | Purpose | Data policy |
|---|---|---|
| local | development + isolated demos | fixtures + synthetic data |
| test | CI: unit/integration/API/golden | recorded fixtures only |
| staging | release validation + print acceptance | sanitised fixtures + approved samples |
| pilot/production | authorised operation | live project/audit/artefact data (hosting = separate owner decision, Stage 7) |

`MAPS4U_ENV` selects the profile; same container image runs everywhere (proposal §16).

### 9.2 Local setup (exact, binding)

```bash
# Prereqs: git, Python 3.12+, docker + compose v2 (host machine)
git clone <repo> maps4u-street-map-system && cd maps4u-street-map-system
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # runtime + pytest/ruff/mypy/hypothesis
make test                        # must be green before anything else
make run                         # api + worker + redis via compose, OR:
docker compose -f docker/docker-compose.yml up -d
# UI: http://localhost:8080  API docs: http://localhost:8080/api/docs
```

**Dev-container variant (no Docker/Redis available — C-6, verified):**

```bash
source /opt/venv/bin/activate
pip install -e ".[dev]"
# run redis via fakeredis or spawn a local redis if permitted; otherwise
MAPS4U_QUEUE=inline pytest           # pipeline runs synchronously in tests
uvicorn maps4u.api.main:app --port 8080 &   # api alone
```

The worker supports an `MAPS4U_QUEUE=inline` mode executing the pipeline in-process for dev/test without Redis — production always uses Celery (guard test asserts compose profile sets it).

### 9.3 Configuration management
- All env vars in §4.3 table only; `.env.example` is canonical; `pydantic-settings` validates at boot; unknown vars fail fast in test env.
- Cartographic config (`styles/`, `config/`) is data, not env — version-controlled, hashed into manifests.

### 9.4 Test data
- `tests/fixtures/`: geofences (Noosa, MCY, synthetic tiny), recorded Overpass responses, minimal style spec, corrections samples (valid + invalid + stale-target).
- Golden artefacts under `tests/e2e/golden/` (canonical layout + PDF structure snapshots).

### 9.5 Staging/print acceptance
- Staging runs the compose stack pinned to a release candidate image digest; printer validation uses physical samples of each paper/orientation (proposal §18 print acceptance); results recorded in `docs/qa-acceptance.md`.
---

## 10. Build sequence (dependency-ordered, agent-executable)

Mapped to the proposal's 8 gated stages. Each stage ends with **checkpoint state** written to `/a0/usr/workdir/mission-checkpoints/maps4u/{stage}.json` (project operating rule 5) and a proceed/stop decision. Tasks use: objective / inputs / actions / outputs / dependencies / acceptance criteria / tests / completion conditions.

### Stage 0 — Reconcile and approve (gate: no unresolved owner-blocking decision)

- **S0.T1 Reconcile sources.** Objective: one authoritative baseline. Inputs: PRD v2, project input, Sept 2026 design proposal + David's note. Actions: create repo skeleton (§4.1) with `docs/prd-v2.md`, `docs/design-proposal-2026-09.md` (copy of the docx content), this plan, ADRs 1–9 drafts. Outputs: repo + docs. Deps: none. Acceptance: docs committed; ADR list matches §2.5. Tests: none (docs). Done when: repo exists with docs and ADR drafts.
- **S0.T2 Owner-decision register.** Objective: track open decisions. Actions: create `docs/decisions.md` from proposal §21 (MCY rights, pilot areas, min type, print standard, insets, hosting, identity, retention, cartographic reviewer) + provisional answers (PA-1..7). Outputs: decision register. Deps: S0.T1. Acceptance: every open item has proposed position + owner + due. Done when: register committed. **This stage can complete while waiting for the owner meeting — the build is designed to be resumable (David: filler project).**

### Stage 1 — Foundation and data (gate: clean build + green CI + fixture fetch/cache proven)

- **S1.T1 Project scaffold.** Obj: runnable skeleton. Actions: `pyproject.toml` (deps §3.1, pinned), package layout §4.1, `core/config.py` (pydantic-settings), `core/db.py` + migration 0001 (schema §5.2 + §5.10), Makefile, `.env.example`, ruff/mypy/pytest config, CI workflow (§12). Outputs: installable package, empty app. Deps: S0.T1. Acceptance: `pip install -e ".[dev]"` works; `make lint test` green with one smoke test. Tests: config loading, migration idempotency. Done: CI green on skeleton.
- **S1.T2 Canvas protocol + inline queue.** Obj: decoupled pipeline runnable without Redis. Actions: `render/canvas.py` protocol; `worker/pipeline.py` stage runner with `MAPS4U_QUEUE=inline`; `core/state.py` state machine. Outputs: stage runner + state tests. Deps: S1.T1. Acceptance: synthetic two-stage pipeline transitions + audit events pass. Tests: unit (state transitions incl. illegal ones), integration (inline pipeline happy path). Done: state machine + inline runner proven.
- **S1.T3 OSM acquisition + cache (TDD).** Obj: fixture-based fetch/cache/provenance. Actions: RED — write failing tests: fetch roads for a recorded bbox fixture → GeoPackage layers with counts; cache hit returns identical snapshot_id; raw bytes stored; retry ladder on simulated failures. GREEN — implement `geo/overpass.py` (fixture mode), `geo/acquire.py`, `geo/cache.py`, `geo/features.py`, `geo/crs.py`. Outputs: working acquisition layer. Deps: S1.T1. Acceptance: all tests green; provenance fields populated (query, source_ts, osm_base_date, sha256). Tests: unit (query build, bbox normalise), integration (fixture fetch→gpkg→reload), failure injection. Done: `pytest tests/integration/test_acquire.py` green; no network in tests (guard test).
- **S1.T4 Corrections loader (TDD).** Obj: validated, idempotent corrections. Actions: RED — failing tests for valid file apply/rename/add/remove/reclass, invalid YAML, unknown osm_id warning, stale-target flag. GREEN — `geo/corrections.py` + `schemas/corrections.schema.json`. Deps: S1.T3. Acceptance: tests green. Done: corrections layer proven.
- **S1.T5 FastAPI skeleton + projects/geofence APIs.** Obj: first real endpoints. Actions: `api/main.py` + `routes_system.py` (health/ready/meta), `routes_projects` (create/list/get, geofence revisions), validation §6.2. Outputs: API + OpenAPI. Deps: S1.T1. Acceptance: TestClient suite green; illegal geometry → 422 with code. Tests: API contract tests. Done: `/api/meta`, `/api/projects*` green.

### Stage 2 — Geometry and viability (gate: all paper/orientation checks pass)

- **S2.T1 Paper templates.** Obj: 6 templates. Actions: `config/paper_templates.yaml` full set + `layout/templates.py` loader + map-area resolver. Tests: each template resolves a positive map_area_mm ≥ 60 % of page minus furniture; fixture table test. Deps: S1.T1. Done: templates testable.
- **S2.T2 Scale + legibility assessment (TDD).** Obj: assessment math §6.3. Actions: RED — failing tests: known extents → expected denominators (± tolerance); undersized-font config → blocked with choices; dense synthetic fixture → density warning; hard failures not overridable. GREEN — `render/assess.py`. Deps: S2.T1, S1.T2. Acceptance: all paper×orientation combos pass for the 3 known pilot geofences. Tests: unit + property (hypothesis: scale monotonicity with area). Done: `POST /api/viability` green end-to-end.
- **S2.T3 Geofence editor UI.** Obj: operator can draw. Actions: `ui/static` Leaflet + draw; project wizard; live scale readout calling `/api/viability`; revision history display. Deps: S2.T2, S1.T5. Acceptance: manual script (docs/runbook.md §operator flows) passes; screenshot fixture for UI smoke. Done: UC-1 + UC-2 usable by a non-developer (NFR-07).

### Stage 3 — Style and basic render (gate: owner approves baseline style direction; requires MCY source files)

- **S3.T1 Cairo canvas + renderer spike (ADR-1).** Obj: prove/choose renderer. Actions: implement `render/cairo_canvas.py`; spike both Cairo and Mapnik on a dense fixture comparing (a)-(d) of §2.4; record ADR-001 outcome. Deps: S1.T2. Acceptance: spike report in `docs/adr/`; chosen renderer passes reproducibility test (two runs → identical content hash under §2.6 standard). Tests: canvas protocol unit tests (path ops, text metrics vs fonttools reference). Done: renderer chosen + locked.
- **S3.T2 Style schema + engine.** Obj: config-driven cartography. Actions: `schemas/style.schema.json`; `render/style_engine.py`; minimal starter style from MCY measurements (manual, `scripts/measure_style.py` helper); z-order + scale-band selection. Deps: S3.T1. Acceptance: invalid style rejected with precise errors; starter style renders fixture roads/water/parks. Tests: unit (z-order, band selection), golden (starter-style fixture draw-log). Done: style engine green.
- **S3.T3 First proof render.** Obj: roads/water/parks PDF for one pilot bbox. Actions: wire transform→style→compose→render stages; thumbnail via PyMuPDF. Deps: S3.T2, S1.T3. Acceptance: A4 landscape proof.pdf generated with vector paths + embedded fonts (pikepdf structural check); thumbnail generated. Tests: PDF structure tests (page box, fonts embedded, has vector ops, no unexpected raster). Done: end-to-end render on cached data (NFR-06 proven: network off).

### Stage 4 — Labels, furniture and QA (gate: golden fixtures + technical PDF checks pass)

- **S4.T1 Label engine (TDD, the hardest component — prototype early on dense fixture per proposal §20).** Obj: deterministic placement. Actions: RED — failing tests: candidate order fixed; metrics match fonttools within tolerance; collision → next candidate → drop with reason; edge clipping rejected; repeats on long roads; seed determinism (same seed → same result; different seed → allowed difference). GREEN — `labels/{candidates,metrics,collision,priority,engine}.py`. Deps: S3.T2. Acceptance: dense urban fixture ≥ 90 % of named arterials/collectors labelled with full drop-report; zero accepted overlaps; zero clipped. Tests: unit per rule + property (no two placed labels intersect; all placed inside frame) + golden label layout fixture. Done: label engine gate green.
- **S4.T2 Furniture + compose.** Obj: complete page. Actions: `layout/furniture.py` + composer; title/north/scalebar/legend/grid/attribution/watermark; frozen layout spec output. Deps: S3.T3. Acceptance: all 6 templates compose without furniture overlap (collision test vs map frame); attribution present. Tests: unit + template composition tests. Done: composed pages for all formats.
- **S4.T3 QA engine + reports.** Obj: governed output set. Actions: `qa/preflight.py` + `qa/report.py`; findings model (blocker/warning/info) → `qa_findings`; md+json renderers; enforce all-four-outputs rule at verify. Deps: S4.T1/T2. Acceptance: injected-failure tests prove each QA category catches its target (min font, collision, clipped, dropped, structure, integrity, empty-map); job with missing output cannot reach proof_ready. Tests: unit per check + integration. Done: QA gate green.
- **S4.T4 Multi-format + insets (flagged).** Obj: all formats + optional inset. Actions: extend templates/composer for inset page when `MAPS4U_INSETS_ENABLED`; reverse-side legend/index. Deps: S4.T2. Acceptance: inset job produces 2-page proof; disabled flag produces 1 page. Tests: composition tests both modes. Done: FR-13 + FR-18(flagged) complete.

### Stage 5 — Review flow and pilot (gate: pilot acceptance evidence complete)

- **S5.T1 Review/approval flow.** Obj: approve/reject immutable proof. Actions: approve/reject endpoints; `review_decisions` with proof checksum; artefact lock; UI proof viewer + QA panel + reject-comment enforcement. Deps: S4.T3. Acceptance: approve locks; material change → new job enforced; reject without comment → 422. Tests: API + integration. Done: FR-15/16/17 green.
- **S5.T2 Reproducibility + manifest.** Obj: regenerate from frozen spec. Actions: `bundle/archive.py` manifest + `reproduce()`; `scripts/verify_determinism.py` (content-hash compare under §2.6 standard). Deps: S5.T1. Acceptance: reproduce(job) → equivalent content/layout/structure + matching hashes; non-matching → failure with diff. Tests: integration golden. Done: NFR-05/01 (revised) green.
- **S5.T3 Pilot runs (3 areas).** Obj: owner/cartographic/print review. Actions: run Noosa + Bribie/Sandstone Point + MCY (or owner-chosen set per decisions register) end-to-end; record owner review; tune style within scope. Deps: S5.T2 + owner inputs. Acceptance: acceptance criteria §19 of proposal all pass; signed evidence in `docs/qa-acceptance.md`. Done: pilot definition of done.

### Stage 6 — Packaging and handover (gate: pilot definition of done signed)

- **S6.T1 Docker packaging.** Obj: one-command pilot. Actions: multi-stage Dockerfile + compose (api, worker, redis; volumes for data); `make run` = `docker compose up`. Deps: S5.T3. Acceptance: clean-machine compose up → working UI + job within NFR-03 times; image scanned (trivy) with no highs. Tests: compose smoke test (offline fixture job). Done: NFR-04 green.
- **S6.T2 Docs + runbooks.** Obj: handover set. Actions: `docs/runbook.md` (operator: new area, review, corrections), `docs/corrections-guide.md` (client-facing), `docs/api.md` (from OpenAPI), `docs/deployment.md`, licensing note, restore drill script + executed backup/restore exercise (proposal §16). Deps: S6.T1. Acceptance: a non-developer can produce a map following only the runbook (UAT §11.7). Done: deliverables of proposal Appendix A present.
- **S6.T3 Final validation.** Obj: pilot sign-off. Actions: full regression + live Overpass smoke + determinism verification across all pilot areas; fix forward. Deps: S6.T2. Acceptance: all gates re-run green; sign-off recorded. Done: MVP complete.

### Stage 7 — Production hardening (SEPARATE owner decision; not authorised by this plan)

Preconditions: owner approves hosting, cost, support + OIDC provider + retention. Work: PostGIS/S3 migration (ADR-2 profile), OIDC + roles, private networking, load testing, operational handover. Entry blocked until `docs/decisions.md` shows the hosting decision ticked. Do not start as part of MVP.

---
## 11. Testing and quality assurance

### 11.1 Levels and tooling

| Level | Proves | Tooling |
|---|---|---|
| Unit + property | geometry, scale, classification, state, label rules across valid/invalid cases | pytest, hypothesis |
| Provider contract | OSM acquisition/parsing vs recorded fixtures, no live network | pytest + fixture mode |
| DB/migration | constraints, idempotency, rollback | pytest + temp SQLite |
| API contract | requests/responses/problem details | FastAPI TestClient + schemathesis-lite |
| Golden layout | stable feature primitives + label placement for approved fixtures | canonical draw-log + layout fixtures |
| PDF structural | page boxes, fonts, vector paths, attribution, no unexpected raster | pikepdf, pypdf, pdfplumber |
| Visual regression (Stage 3+) | rendered reference images within approved tolerance | PyMuPDF raster + pixel-diff with threshold |
| E2E | operator create→render→review→approve | compose smoke (offline) + manual UAT script |
| Performance/resilience | NFR-03 job sizes; worker/provider failure recovery | timed fixtures + failure injection |
| Print acceptance | printer accepts each format's physical samples | staging + printer (proposal §18) |

### 11.2 TDD policy (binding, C-3)
Every cartographic rule and pipeline stage: failing test first (commit the RED), then minimal implementation (GREEN), refactor. Reviewer checklist rejects merged code without a paired test for each rule.

### 11.3 No-network rule
All automated tests run offline: Overpass fixtures, vendored tiles stubs, `MAPS4U_QUEUE=inline`. A guard test asserts no socket connections during the suite (except explicit `-m live`).

### 11.4 Coverage policy
≥ 85 % lines on `core`, `geo`, `render`, `labels`, `qa` (NFR-11); enforced in CI; exclusions documented.

### 11.5 Golden-test policy (per proposal §13)
Golden comparisons use **canonical layouts + PDF structure**, not raw bytes: normalise (parse draw-log/layout spec + pikepdf structure), hash, compare. Byte comparison only where metadata normalisation is proven (ADR-4).

### 11.6 Fixtures
Dense-urban fixture (label stress, prototype early), sparse-rural, coastal (water/coastline), tiny synthetic (fast unit), three pilot geofences. Owner-nominated pilot areas recorded in decisions register.

### 11.7 UAT script (NFR-07)
A non-developer follows `docs/runbook.md` alone: create project → draw geofence → assess → submit → open proof + QA → reject with comment → upload correction → re-render → approve → verify bundle. Pass = completed without developer help; recorded in `docs/qa-acceptance.md`.

### 11.8 Phase gates (what must pass to progress)

| Gate | Must pass |
|---|---|
| G1 (Stage 1) | clean install, CI green, fixture acquisition + corrections proven, state machine auditable |
| G2 (Stage 2) | viability math correct for all paper×orientation; UI usable by operator |
| G3 (Stage 3) | renderer spike decision recorded; starter style renders pilot fixture; vector PDF + structural checks pass offline |
| G4 (Stage 4) | label engine deterministic + drop-report complete; all templates compose; QA catches every injected failure |
| G5 (Stage 5) | review/approval immutable; reproduce() equivalent; 3 pilot areas pass owner/cartographic/print review |
| G6 (Stage 6) | compose one-command deploy; runbook-only UAT passes; backup-restore drill done |
| G7 (Stage 7) | production checklist (only after owner hosting decision) |
---

## 12. DevOps and deployment

### 12.1 CI/CD (pilot: GitHub Actions if a remote exists; otherwise local git hooks performing the same gates)

Pipeline on every push: ruff → mypy (strict on core/geo/qa) → pytest unit/property → pytest integration (offline fixtures) → coverage ≥ 85 % → pip-audit → build image → trivy image scan (block on high/critical) → compose smoke test (offline end-to-end job) → tag `sha` image. Release (manual tag `vX.Y.Z`): staging deploy → print-acceptance samples → pilot upgrade instructions.

### 12.2 Infrastructure provisioning
Pilot: `docker/docker-compose.yml` (services: api, worker, redis; volumes: data for /data; only api port published on localhost). Infrastructure-as-code: the compose file + Dockerfile ARE the pilot IaC. Production (Stage 7): Terraform/CDK defined then, under the hosting decision — out of MVP scope.

### 12.3 Application deployment (pilot)

```bash
cd maps4u-street-map-system
docker compose -f docker/docker-compose.yml pull   # or build
docker compose -f docker/docker-compose.yml up -d
# migrations run automatically at api startup (idempotent, transactional)
curl -f http://localhost:8080/healthz && curl -f http://localhost:8080/readyz
```

### 12.4 Database migration strategy
Numbered SQL migrations applied in-order at startup inside a transaction; `schema_migrations` tracks versions (§5.2). Rollback for pilot = restore last nightly backup (§5.8); documented restore drill required before any claim of recoverability (proposal §16). Down-migrations are not provided in MVP; additive changes preferred.

### 12.5 Rollback strategy
Images are immutable digests; rollback = previous tag. Data: pilot restores SQLite + artifacts volume from nightly backup; the drill is scripted (`scripts/restore_drill.sh`) and exercised at Stage 6.

### 12.6 Release management
Semantic versions; changelog per release; every release bundles: image digest, style versions, font hashes, migration set, release notes; the reproducibility manifest links the exact digests. Owner sign-off recorded for pilot releases (governance §22 of proposal).

---

## 13. Observability and operations

### 13.1 Logging
structlog JSON to stdout (compose collects); levels via `MAPS4U_LOG_LEVEL`. Every log line: request_id/job_id, stage, event. No secrets/tokens (redaction middleware, §8.6).

### 13.2 Metrics and monitoring (pilot-appropriate)
Prometheus-format `/metrics` endpoint: jobs by status, stage durations, queue depth, Overpass fetch count/failures, cache hit rate, render durations, PDF sizes. Local Prometheus+Grafana optional profile (`docker compose --profile metrics`). Health: `/healthz` (liveness) + `/readyz` (db, redis, worker ping).

### 13.3 Tracing
Stage-level tracing via job_events (each stage records start/end/duration) — the audit log IS the trace for a single-operator pilot; OpenTelemetry deferred to Stage 7 with justification in ADR register.

### 13.4 Alerting
Pilot: simple log-based alerts (failed jobs, E_OVERPASS_UNAVAILABLE streaks, disk > 80 %) surfaced in the UI banner + a daily digest file. Hosted alerting is Stage 7.

### 13.5 Cost monitoring
Pilot costs = operator laptop + Overpass quota (free, monitored via fetch metrics + cache hit rate). No cloud spend before Stage 7; the Stage 7 proposal must include a cost model (proposal §16 owner approval of hosting/cost).

### 13.6 Incident response
`docs/runbook.md` §troubleshooting: symptoms → checks → fixes for the 7 failure modes of §7.4 + restore procedure. Pilot incidents are operator-actionable; production IR plan is Stage 7.

---

## 14. Documentation (what/when)

| Doc | Produced at |
|---|---|
| `docs/prd-v2.md`, `docs/design-proposal-2026-09.md`, this plan, `docs/adr/*` | Stage 0 |
| `docs/decisions.md` (owner decision register) | Stage 0, maintained throughout |
| `docs/testing.md`, CI docs | Stage 1 |
| `docs/licensing.md` (ODbL/OFL obligations) | Stage 3 |
| `docs/api.md` (from OpenAPI export) | Stage 5, refreshed at 6 |
| `docs/qa-acceptance.md` (UAT + pilot sign-off log) | Stage 5–6 |
| `docs/runbook.md` (operator), `docs/corrections-guide.md` (client), `docs/deployment.md`, `docs/threat-model.md` (final), restore drill | Stage 6 |
| README (quickstart) | Stage 1, kept current |

Every doc states the exact version/date of the system it describes (proposal governance: exact versions at each stage end).

---

## 15. Delivery roadmap

| Milestone | Content | Depends on |
|---|---|---|
| M0 Baseline approved | repo, docs, ADRs, decision register | owner meeting (Stage 0) |
| M1 Foundation | scaffold, CI, acquisition+cache+corrections, state machine, projects API | M0 |
| M2 Operator UX | geofence editor, viability for all formats | M1 |
| M3 First proof | renderer chosen (spike), starter style, vector PDF + thumbnail offline | M2 + MCY source files (owner input!) |
| M4 Cartographic core | deterministic labels, furniture, QA engine, all formats + insets | M3 |
| M5 Governed production | review flow, reproducibility, 3-area pilot sign-off | M4 + owner review cycles |
| M6 Handover | Docker package, runbooks, UAT, restore drill — **MVP complete** | M5 |
| M7 Production hardening | hosting/OIDC/PostGIS/S3/load tests | separate owner decision (NOT MVP) |

**Critical path:** M0 → M1 → M2 → M3 → M4 → M5 → M6. The highest-risk items sit early: **M3 renderer spike** and **M4 label engine** (validate both on the dense-urban fixture before committing downstream work — proposal §20). Owner-input dependencies (MCY files, pilot areas, print standard) gate M3 and M5 — surface at every checkpoint.

**Schedule note (David, 11 Aug 2026):** secondary/filler priority — stages are designed to pause/resume cleanly between checkpoints; no stage assumes continuous availability.

---

## 16. Risks and unknowns

| # | Risk | Type | Mitigation/validation |
|---|---|---|---|
| R-1 | MCY style reproduction rights unclear | commercial/legal | Confirm ownership/permission BEFORE style implementation (Stage 0 decision; proposal §20) |
| R-2 | Reference PDF lacks exact fonts/colours | data | Obtain printer/source files or formally approve measured approximations (recorded per value, §5.5) |
| R-3 | OSM incomplete/out-of-date | data | Coverage QA + source-date visibility + corrections file |
| R-4 | Large areas can't stay legible | technical/product | Pre-render assessment + explicit user choice (hard failures not overridable) |
| R-5 | Dense labels unreadable | technical | Prototype collision behaviour EARLY on dense fixture (S4.T1 prototyped in Stage 3 spike work); cartographic review |
| R-6 | Font/native-lib changes alter output | technical | Bundle+hash fonts, pin image, golden tests (ADR-4) |
| R-7 | Overpass throttling | integration | Aggressive cache, bounded queries; self-host/managed source option (ADR-5) |
| R-8 | Browser preview ≠ print PDF | product | Preview marked secondary; PDF is the sole approval artefact |
| R-9 | AI introduces inconsistency | technical | AI outside deterministic production path (binding) |
| R-10 | 12-week pilot absorbs production concerns | delivery | Pilot completion gated separately from hosting/security hardening (Stage 7 split) |
| R-11 | Mapnik/Cairo wheel instability (py3.12/ARM) | technical | ADR-1 spike decides empirically; ReportLab fallback documented |
| R-12 | SQLite → PostGIS migration cost | architecture | Identical column semantics (§5.10); migration is a scripted Stage 7 task, not a rewrite |
| R-13 | Owner-review latency (filler project) | delivery | Checkpointed resumable stages; provisional answers keep build moving |
| R-14 | Disk exhaustion from extracts/artefacts | operations | Retention policy decision (Stage 0), volume monitoring, purge tooling at Stage 6 |

---

## 17. Agent execution instructions

### 17.1 Execution contract

1. Work strictly in stage/task order (§10). A task is done only when its acceptance criteria + tests + completion conditions are verified green — never when it merely runs.
2. TDD: write the failing test, commit conceptually, implement minimally, refactor (§11.2).
3. No cartographic constants in code; all in `styles/` + `config/` (C-2). A reviewer checklist enforces this.
4. After every stage: write checkpoint JSON to `/a0/usr/workdir/mission-checkpoints/maps4u/{stage}.json` containing: stage, tasks completed, tests passing count, known limitations, exact versions, open owner decisions, proceed/stop recommendation.
5. Surface owner-blocking decisions immediately in the response, not buried in checkpoints (MCY files, pilot areas, print standard, min-type confirmation).
6. Never start Stage 7 work. Never implement advertising/QR/M2G/DDD/GBP/portal (C-1). If a task appears to require them, stop and report.
7. Determinism policy ADR-4/ADR-9 governs all render/label code: seeded, stable-ordered, content-hash verified.

### 17.2 Stage-entry inspection (do before each stage)

Before starting stage N: read the last checkpoint; run the full test suite; confirm the stage's dependencies (owner inputs, prior gates) are satisfied; if not, report the blocker and stop. Do not partially start gated stages.

### 17.3 Verification commands (canonical)

```bash
make lint            # ruff + mypy
make test            # full offline suite
make test-cov        # with coverage gate 85%
pytest -m live       # optional, manual, real Overpass only
docker compose -f docker/docker-compose.yml up -d && curl -f localhost:8080/readyz
python scripts/verify_determinism.py --job <job_id>   # reproduce + content-hash compare
```

### 17.4 Definition of done (MVP)

All of: G1–G6 green; acceptance criteria of proposal §19 all met; UAT passed by non-developer using only runbook; backup-restore drill executed; 3 pilot areas signed off; reproducibility verified; deliverables of proposal Appendix A present; `docs/decisions.md` shows every owner decision resolved or explicitly deferred to Stage 7.

---

## Appendices

### Appendix A — Traceability: proposal acceptance criteria → plan

| Proposal §19 criterion | Covered by |
|---|---|
| Project + valid geofence revision | F-01, §5.10, S1.T5, S2.T3 |
| Every paper/orientation selectable + assessed | §5.4, S2.T1/T2 |
| System explains legibility failure | §6.3, S2.T2 |
| OSM cached, attributable, provenance-linked | §5.7, S1.T3 |
| Style = versioned config, no hidden constants | §5.5, S3.T2, C-2 |
| Deterministic labels + omission reporting | §6.7, S4.T1 |
| Valid vector PDF, approved fonts, furniture | §6.9, S3.T3, S4.T2 |
| Every successful job: proof+QA+manifest (+thumbnail) | §2.3 rule, S4.T3 |
| Reviewer approves/rejects exact immutable proof | §6.10, S5.T1 |
| Material change → new render + approval | ADR-8, §6.1 |
| Frozen job reproducible | ADR-4, S5.T2 |
| ≥3 pilot areas pass owner/cartographic/print review | S5.T3, §11.7 |

### Appendix B — Suggested commit sequence (first 10)

1. `chore: scaffold repo, docs, ADR drafts` (S0.T1)
2. `feat(core): config + db migrations + state machine` (S1.T1/T2)
3. `test(geo): RED overpass fixture fetch` → `feat(geo): acquisition + cache + provenance` (S1.T3)
4. `test(geo): RED corrections` → `feat(geo): corrections loader` (S1.T4)
5. `feat(api): meta/health + projects/geofence endpoints` (S1.T5)
6. `feat(layout): paper templates + resolver` (S2.T1)
7. `test(render): RED assessment` → `feat(render): scale + legibility` (S2.T2)
8. `feat(ui): Leaflet geofence editor + viability readout` (S2.T3)
9. `spike(render): cairo vs mapnik — ADR-001 decision` (S3.T1)
10. `feat(render): canvas impl + style schema + first proof` (S3.T2/T3)

### Appendix C — Binding interface snippets (v1 reference)

Canvas protocol (see §7.2 for module signatures):

```python
class Canvas(Protocol):
    def set_page(self, size_mm: tuple[float, float], bleed_mm: float) -> None: ...
    def path(self, ops: PathOps, stroke: Stroke | None, fill: Fill | None) -> None: ...
    def text(self, glyphs: list[GlyphPlacement]) -> None: ...   # per-glyph, exact metrics
    def embedded_font(self, ttf_path: Path) -> str: ...          # returns font id; subset embed
    def save_pdf(self, path: Path) -> None: ...                  # metadata stripped/normalised
```

Draw-log (testable): every save also emits a canonical JSON op-log at `<artifacts>/drawlog.json` — the golden-test substrate (§11.5).

### Appendix D — Paper template set
A3/A4/A5 × landscape/portrait = 6 templates; page sizes 420×297, 297×210, 420×297(portrait swaps), 297×420, 210×148, 148×210 mm; margins 15 mm (A3), 12 mm (A4), 10 mm (A5); furniture cells per §5.4; trim/bleed fields present from v1 (printer decision fills exact bleed, Stage 0).

### Appendix E — Determinism checklist (every render code review)

- [ ] No wall-clock/random/file-order inputs into placement or styling
- [ ] Seeds explicit and recorded in render spec
- [ ] Stable sorts everywhere (never bare dict/set iteration)
- [ ] Coordinates quantised to render units before output
- [ ] Fonts loaded from vendored hashed TTFs only
- [ ] PDF metadata normalised (producer, dates, IDs)
- [ ] Golden draw-log/PDF-structure comparison in CI for fixtures

### Appendix F — Owner decision register (seed from proposal §21)

MCY reference + reproduction rights · pilot areas · minimum printed type · print standard/colour space/bleed · inset/reverse side · hosting · OIDC provider · retention · cartographic reviewer. Each: proposed position (PA-1..7) · status (open/approved/deferred-to-7) · date. **Live copy of this register is `docs/decisions.md` in the repo.**

### Appendix G — Glossary
Proof (governed PDF pending approval) · Furniture (title/legend/scale/north/grid/attribution) · Geofence revision (immutable boundary version) · Render specification (frozen job inputs, ADR-8) · Governed output set (proof+thumbnail+QA+manifest) · Scale band (style visibility/simplification rule) · Golden test (canonical layout/structure comparison) · Pilot (local Docker deployment profile).

### Appendix H — PROVISIONAL items awaiting owner confirmation

PA-1 MCY source files + rights (blocks Stage 3) · PA-2 pilot areas (blocks Stage 5) · PA-3 web geofence tool (adopted) · PA-4 1.5 mm min type, pilot-only (adopted pending printed samples) · PA-5 RGB vector PDF first, PDF/X path documented (printer to confirm) · PA-6 local Docker pilot, hosting deferred to Stage 7 decision · PA-7 insets optional/flagged · plus: retention periods, cartographic reviewer identity, OIDC provider, owner-decision tick verification from the annotated document.

*End of plan.*
