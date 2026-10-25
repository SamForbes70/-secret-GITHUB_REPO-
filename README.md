# Maps4U Street Map System (`maps4u-maps` v1.0.2)

![Release](https://img.shields.io/badge/release-v1.0.4-blue)
![Python](https://img.shields.io/badge/python-3.12%2B%20%7C%203.13-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688)
![Tests](https://img.shields.io/badge/tests-95%2F95%20passing-brightgreen)
![Determinism](https://img.shields.io/badge/PDF%20Determinism-SHA--256%20Verified-success)
![Map Data](https://img.shields.io/badge/Data-%C2%A9%20OpenStreetMap%20ODbL-7EBC6F)

A deterministic, config-driven cartographic production pipeline that converts an operator-drawn geofence (`EPSG:4326` GeoJSON `Polygon` / `MultiPolygon`) and a print paper specification (`A3`, `A4`, `A5` in `landscape` or `portrait`) into a print-ready vector PDF street map (`proof.pdf`), raster preview (`thumb.png`), automated QA preflight report (`qa-report.json` + `qa-report.md`), and cryptographic provenance manifest (`manifest.json`), styled after the **Maroochydore (`MCY`)** reference street map.

---

## Table of Contents

1. [System Highlights & Core Guarantees](#1-system-highlights--core-guarantees)
2. [End-to-End Pipeline Architecture](#2-end-to-end-pipeline-architecture)
3. [Complete Beginner's Guide: How to Download & Run Maps4U Step-by-Step](#3-complete-beginners-guide-how-to-download--run-maps4u-step-by-step)
4. [Developer Quickstart & End-to-End API Walkthrough](#4-developer-quickstart--end-to-end-api-walkthrough)
5. [Governed 5-Artifact Output Bundle](#5-governed-5-artifact-output-bundle)
6. [Paper Templates & Viability Rules](#6-paper-templates--viability-rules)
7. [Repository Structure](#7-repository-structure)
8. [Configuration & Environment Variables](#8-configuration--environment-variables)
9. [Testing, QA & Reproducibility Verification](#9-testing-qa--reproducibility-verification)
10. [Documentation & Governance Index](#10-documentation--governance-index)
11. [Acknowledgements & Special Thanks to Winston the Cat](#11-acknowledgements--special-thanks-to-winston-the-cat)

---

## 1. System Highlights & Core Guarantees

- **100% Deterministic Vector PDF Output:** Given identical frozen inputs (`RenderSpec`, cached OpenStreetMap `.gpkg` snapshot, YAML style, and optional YAML client corrections), `CairoCanvas` emits **byte-for-byte identical** PDF 1.4 vector streams (`proof.pdf`) and identical `content_hash()` draw logs across repeated executions.
- **Zero Hardcoded Cartography:** All colours, road casing/fill widths, font families, font heights (`mm`), halo widths, z-order layers, and scale-band simplification rules reside in `styles/mcy/v1/style.yaml` (validated against `schemas/style.schema.json`).
- **Hard Minimum Font Legibility Gate (`1.5 mm`):** Both pre-job viability assessment (`POST /api/viability`) and post-render QA preflight (`src/maps4u/qa/preflight.py`) enforce a non-overridable **1.5 mm minimum printed text height** floor.
- **Collision-Free `STRtree` Label Placement:** Priority-ordered placement (`suburb` → `landmark` → `arterial` → `collector` → `local` → `service`) using Shapely `STRtree` spatial indexing guarantees zero overlapping labels and zero frame-clipped labels.
- **Non-Destructive Client Corrections:** Operator YAML corrections (`rename`, `reclass`, `add`, `remove`) are validated against `schemas/corrections.schema.json` and applied in memory over immutable OpenStreetMap GeoPackage caches.
- **Governed State Machine & Cryptographic Approval Locking:** A job cannot transition to `proof_ready` until all 5 governed artifacts exist and pass QA preflight. Approving a proof (`POST /api/jobs/{job_id}/approve`) locks `proof_sha256` in `review_decisions` and transitions the job to `finalized`.

---

## 2. End-to-End Pipeline Architecture

```text
+-----------------------------------------------------------------------------+
|                        Operator Web UI (Leaflet) / HTTP API                 |
|   Draw Geofence (WGS84) -> Select Paper (A3/A4/A5) -> POST /api/viability   |
+--------------------------------------+--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                  Frozen RenderSpec & 11-Stage Job State Machine             |
|  created -> validating -> queued -> assessing -> acquiring -> transforming  |
|  -> styling -> labelling -> composing -> rendering -> verifying             |
|  -> proof_ready -> finalized / rejected                                     |
+--------------------------------------+--------------------------------------+
                                       |
        +------------------------------+------------------------------+
        |                              |                              |
        v                              v                              v
+---------------+            +-------------------+          +-----------------+
| OSM Overpass  |            | YAML Style Engine |          | Map Furniture & |
| & 8-Layer     |            | (styles/mcy/v1)   |          | STRtree Labels  |
| .gpkg Cache   |            | + Client YAML     |          | Grid, Index,    |
| (SHA-256)     |            | Corrections       |          | Scale, ODbL     |
+-------+-------+            +---------+---------+          +--------+--------+
        |                              |                             |
        +------------------------------+-----------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                   Governed Output Bundle (/var/jobs/<job_id>/)              |
|   1. proof.pdf      (Vector PDF 1.4 with MediaBox/TrimBox/BleedBox)         |
|   2. thumb.png      (Raster preview thumbnail)                              |
|   3. qa-report.json (Machine-readable 7-gate QA preflight report)           |
|   4. qa-report.md   (Human-readable Markdown QA preflight summary)          |
|   5. manifest.json  (Cryptographic SHA-256 provenance manifest)             |
+-----------------------------------------------------------------------------+
```

---

## 3. Complete Beginner's Guide: How to Download & Run Maps4U Step-by-Step

New to GitHub, Docker, or Python? **Start here!** This section walks you through every single step from downloading the project onto your computer to generating and opening your first print-ready PDF street map. *(Also available as a standalone guide in [`docs/getting-started-beginners.md`](docs/getting-started-beginners.md).)*

### Step 1: Download the Project to Your Computer

You can get the files in one of two ways:

- **Way 1 — Download as a ZIP file (No Git required):**
  1. Scroll to the top of this GitHub page and click the green **`<> Code`** button.
  2. Click **Download ZIP**.
  3. Unzip/extract the downloaded folder (`maps4u-street-map-system-main`) to somewhere easy to find, such as your `Desktop` or `Documents` folder.
- **Way 2 — Using Git (if you have Git installed):**
  Open your terminal (macOS/Linux) or PowerShell/Command Prompt (Windows) and run:
  ```bash
  git clone https://github.com/SamForbes70/maps4u-street-map-system.git
  cd maps4u-street-map-system
  ```

---

### Step 2: Open a Terminal Inside the Project Folder

If you downloaded the ZIP file, open your terminal inside that unzipped folder:
- **Windows:** Open the unzipped folder in File Explorer, click in the address bar at the top, type `powershell`, and press **Enter**.
- **macOS:** Right-click (or two-finger click) the unzipped folder in Finder and select **New Terminal at Folder**.
- **Linux:** Right-click inside the folder and select **Open in Terminal**.

To confirm you are in the right place, type `ls` (or `dir` on Windows) and press **Enter** — you should see files like `README.md`, `Dockerfile`, `docker-compose.yml`, and `pyproject.toml`.

---

### Step 3: Start the Program (Choose Option A *or* Option B)

You only need **one** of the two methods below. **Option A (Docker)** is the easiest because it installs everything automatically inside an isolated container.

#### Option A: Run with Docker Desktop (Easiest — Windows, macOS, Linux)

1. **Prerequisite:** Install and open [Docker Desktop](https://www.docker.com/products/docker-desktop/) so the Docker whale icon is running.
2. **Start Maps4U:** In your terminal, copy and paste this command and press **Enter**:
   ```bash
   export MAPS4U_OPERATOR_TOKEN="local-operator-secret-token-2026"
   export MAPS4U_REVIEWER_TOKEN="local-reviewer-secret-token-2026"
   docker compose up --build
   ```
   *(On Windows PowerShell: `$env:MAPS4U_OPERATOR_TOKEN="local-operator-secret-token-2026"; $env:MAPS4U_REVIEWER_TOKEN="local-reviewer-secret-token-2026"; docker compose up --build`)*
3. **What happens next:**
   - The first time you run this, Docker will download Python and the mapping libraries (takes about 1–3 minutes).
   - Once ready, you will see a line saying:
     `Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`
4. **Open the App:** Open your web browser (Chrome, Edge, Firefox, Safari) and go to:
   **`http://localhost:8000`**

#### Option B: Run Directly with Python (No Docker required)

1. **Prerequisite:** Have **Python 3.12 or 3.13** installed ([python.org/downloads](https://www.python.org/downloads/)).
2. **Create a virtual environment & install the program:**
   - **On macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install --upgrade pip
     pip install -e ".[dev]"
     cp .env.example .env
     ```
   - **On Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     pip install --upgrade pip
     pip install -e ".[dev]"
     Copy-Item .env.example .env
     ```
3. **Start the Web Server:**
   ```bash
   MAPS4U_QUEUE=inline uvicorn maps4u.api.main:create_app --factory --host 127.0.0.1 --port 8080
   ```
   *(On Windows PowerShell, run `$env:MAPS4U_QUEUE="inline"; uvicorn maps4u.api.main:create_app --factory --host 127.0.0.1 --port 8080`)*
4. **Open the App:** Open your web browser and go to:
   **`http://127.0.0.1:8080`**

---

### Step 4: Create Your First Street Map in 60 Seconds (Using the Web Console)

Once you have opened `http://localhost:8000` (Docker) or `http://127.0.0.1:8080` (Python) in your browser:

1. **Load or Draw an Area (Geofence):**
   - Look at the interactive map on the screen. You can click the **Maroochydore Preset** button (or use the polygon drawing tool on the map to click 4 corners around your chosen neighborhood and click the first point again to close the shape).
2. **Pick Your Paper Size & Orientation:**
   - Choose **`A4`** (or `A3` / `A5`) and **`landscape`** (or `portrait`).
3. **Click "Check Viability":**
   - Maps4U immediately calculates the exact print scale (for example, `1:12,500`) and checks whether every street name will print at **`1.5 mm` or larger**.
   - If the area you drew is too large for the paper size (making street names too tiny to read), the system will show a friendly red **Blocker** message and suggest switching to **`A3`** or drawing a smaller box.
4. **Create & Run the Map Job:**
   - Enter a project name (e.g., `My First Map`), click **Save Geofence & Create Job**, and click **Run Render Pipeline**.
5. **View & Download Your Map Bundle:**
   - Within seconds, your job reaches **`proof_ready`**!
   - Click **`proof.pdf`** to open and download your crisp, print-ready vector PDF street map (complete with road casings, parks, waterways, alphanumeric grid `A1..H6`, street index, scale bar, north arrow, legend, and OpenStreetMap attribution).
   - Click **`thumb.png`** to view the quick preview image, or **`qa-report.md`** to read the automated 7-gate quality report.
6. **Approve or Request Corrections:**
   - Click **Approve** to cryptographically lock your final PDF (`finalized`), or submit a YAML correction (for example, renaming a street or adding a local landmark) to spin up a new revision.

---

### Step 5: How to Run the Offline Self-Test (Optional)

Want to verify that everything on your computer works without even using the internet? Run the built-in offline test suite:

```bash
pytest -q
```

You should see `95 passed` — confirming that map acquisition, styling, label placement, PDF generation, QA checks, security controls, and backups all work identically on your machine.

---

### Step 6: How to Stop the Program

- **If running in the terminal:** Press **`Ctrl + C`** in the terminal window.
- **If running in Docker in the background:** Run:
  ```bash
  docker compose down
  ```

---

## 4. Developer Quickstart & End-to-End API Walkthrough

```bash
# 1. Create a map project
PROJECT_ID=$(curl -s -X POST http://127.0.0.1:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{"area_name": "Maroochydore", "reference": "MCY-PILOT"}' | jq -r .project_id)

# 2. Save an immutable WGS84 geofence revision
REV_ID=$(curl -s -X POST http://127.0.0.1:8080/api/projects/${PROJECT_ID}/geofence \
  -H "Content-Type: application/json" \
  -d '{
    "type": "Polygon",
    "coordinates": [[[
      [153.085, -26.660],
      [153.105, -26.660],
      [153.105, -26.645],
      [153.085, -26.645],
      [153.085, -26.660]
    ]]]
  }' | jq -r .revision_id)

# 3. Check print scale & font legibility viability
curl -s -X POST http://127.0.0.1:8080/api/viability \
  -H "Content-Type: application/json" \
  -d '{
    "geofence": {
      "type": "Polygon",
      "coordinates": [[[
        [153.085, -26.660], [153.105, -26.660],
        [153.105, -26.645], [153.085, -26.645],
        [153.085, -26.660]
      ]]]
    },
    "paper": "A4",
    "orientation": "landscape"
  }' | jq .

# 4. Create a frozen render job and execute the 11-stage pipeline
JOB_ID=$(curl -s -X POST http://127.0.0.1:8080/api/jobs \
  -H "Content-Type: application/json" \
  -d "{
    \"project_id\": \"${PROJECT_ID}\",
    \"geofence_revision\": \"${REV_ID}\",
    \"paper\": \"A4\",
    \"orientation\": \"landscape\",
    \"edition\": \"2026-10\"
  }" | jq -r .job_id)

curl -s -X POST http://127.0.0.1:8080/api/jobs/${JOB_ID}/run | jq .

# 5. Download governed outputs
curl -fsS http://127.0.0.1:8080/api/jobs/${JOB_ID}/artifacts/proof.pdf -o proof.pdf
curl -fsS http://127.0.0.1:8080/api/jobs/${JOB_ID}/artifacts/qa-report.md

# 6. Approve and cryptographically lock proof_sha256
curl -s -X POST http://127.0.0.1:8080/api/jobs/${JOB_ID}/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "operator", "comment": "QA passed; approved for print."}' | jq .
```

---

## 5. Governed 5-Artifact Output Bundle

Every completed job writes its governed bundle to `<MAPS4U_ARTIFACT_DIR>/<job_id>/`. The state machine blocks transition to `proof_ready` (`E_GOVERNED_OUTPUT_MISSING`) unless all 5 files exist and are non-empty:

| Artifact | Media Type | Purpose |
| :--- | :--- | :--- |
| `proof.pdf` | `application/pdf` | Print-ready vector PDF 1.4 with exact `MediaBox`, `TrimBox`, `BleedBox`, embedded TrueType font descriptors, road hierarchy, collision-free labels, and map furniture. |
| `thumb.png` | `image/png` | High-contrast raster preview thumbnail for rapid operator visual inspection in the Web UI. |
| `qa-report.json` | `application/json` | Machine-readable QA preflight verdict (`passed`, `blocker_count`, `min_font_mm_observed`, `overlaps`, `clipped`, `structural_checks`, `findings`). |
| `qa-report.md` | `text/markdown` | Human-readable Markdown QA summary table for operator and audit review. |
| `manifest.json` | `application/json` | Cryptographic provenance manifest recording `spec_id`, `snapshot_sha256`, `style_sha256`, `corrections_sha256`, `pdf_sha256`, and `content_hash`. |

---

## 6. Paper Templates & Viability Rules

Defined in `config/paper_templates.yaml` with **3.0 mm bleed** on all edges:

| Template Key | Trim Size (`W × H mm`) | Margins (`mm`) | Grid Cell (`mm`) | Scale Bands Supported |
| :--- | :--- | :--- | :--- | :--- |
| `A3-landscape` | `420.0 × 297.0` | `15.0` | `40.0` | `detail`, `standard_street`, `overview` |
| `A3-portrait` | `297.0 × 420.0` | `15.0` | `40.0` | `detail`, `standard_street`, `overview` |
| `A4-landscape` | `297.0 × 210.0` | `12.0` | `35.0` | `detail`, `standard_street`, `overview` |
| `A4-portrait` | `210.0 × 297.0` | `12.0` | `35.0` | `detail`, `standard_street`, `overview` |
| `A5-landscape` | `210.0 × 148.0` | `10.0` | `30.0` | `detail`, `standard_street` |
| `A5-portrait` | `148.0 × 210.0` | `10.0` | `30.0` | `detail`, `standard_street` |

---

## 7. Repository Structure

```text
maps4u-street-map-system/
├── .github/
│   ├── ISSUE_TEMPLATE/             # Bug report & feature request templates
│   └── PULL_REQUEST_TEMPLATE.md    # Pull request review checklist
├── config/
│   ├── logging.yaml                # Structured logging configuration
│   ├── paper_templates.yaml        # 6 A3/A4/A5 landscape & portrait templates
│   └── settings.yaml               # Geofence limits, Overpass backoff & defaults
├── docs/
│   ├── adr/                        # Architectural Decision Records (ADR-0001..0009)
│   ├── api.md                      # Complete HTTP API Reference
│   ├── architecture.md             # System architecture, state machine & DB schema
│   ├── corrections-guide.md        # Non-destructive client YAML corrections guide
│   ├── decisions.md                # Owner Decision Register (OD-1..OD-9)
│   ├── deployment.md               # Docker Compose deployment & backup/restore guide
│   ├── development-plan.md         # Master engineering specification (MAPS4U-PLAN-001)
│   ├── getting-started-beginners.md# Step-by-step zero-assumption beginner guide
│   ├── prd-v2.md                   # Machine PRD v2 specification
│   ├── qa-acceptance.md            # 3-Pilot QA & reproducibility acceptance report
│   ├── runbook.md                  # Step-by-step operator runbook
│   ├── style-guide.md              # Cartographic YAML style authoring guide
│   ├── testing.md                  # TDD policy, test tiers & verification guide
│   └── threat-model.md             # Security & operational threat model
├── schemas/
│   ├── corrections.schema.json     # JSON Schema for client YAML corrections
│   ├── job.schema.json             # JSON Schema for frozen render specifications
│   └── style.schema.json           # JSON Schema for cartographic style YAML
├── scripts/
│   ├── backup_and_verify.py        # Git bundle, tarball & SHA-256 backup generator
│   ├── backup_restore_drill.py     # Online SQLite WAL + artifact backup/restore drill
│   ├── generate_testing_record_pdf.py # Generates the 3-page PDF testing record
│   ├── smoke_test.py               # Phase 0 / Stage 1 offline pipeline smoke test
│   └── verify_determinism.py       # Repeat-render SHA-256 determinism verifier
├── src/maps4u/
│   ├── api/                        # FastAPI app factory & routers
│   ├── bundle/                     # Provenance manifest & reproduce() verifier
│   ├── core/                       # Config, SQLite WAL DB, state machine, IDs, errors
│   ├── geo/                        # Overpass QL, 8-layer GeoPackage cache, CRS, corrections
│   ├── labels/                     # STRtree collision-free label placement engine
│   ├── layout/                     # Paper templates & map furniture composer
│   ├── qa/                         # 7-gate QA preflight engine & report writers
│   ├── render/                     # Viability assessor, YAML style engine, CairoCanvas
│   ├── ui/static/                  # Static Leaflet operator web console
│   └── worker/                     # Celery app & 11-stage JobExecutor pipeline
├── styles/mcy/v1/
│   └── style.yaml                  # Maroochydore (MCY) v1 cartographic style definition
├── tests/
│   ├── api/                        # FastAPI endpoint & review workflow tests
│   ├── fixtures/                   # Recorded Overpass JSON, geofences & YAML fixtures
│   ├── integration/                # Stage 1–6 end-to-end & multi-pilot integration tests
│   └── unit/                       # Unit & Hypothesis property-based tests
├── CHANGELOG.md                    # Release history across Gates G1–G6
├── CODE_OF_CONDUCT.md              # Community Code of Conduct
├── CONTRIBUTING.md                 # Developer & TDD contribution guidelines
├── Dockerfile                      # Multi-stage Python 3.13 slim production image
├── docker-compose.yml              # API + Celery Worker + Redis 7 orchestration
├── LICENSE                         # License & OpenStreetMap ODbL attribution terms
├── Makefile                        # Developer lint, test, coverage, and run targets
├── pyproject.toml                  # Package metadata, dependencies, ruff, mypy, pytest
└── SECURITY.md                     # Security policy & vulnerability reporting
```

---

## 8. Configuration & Environment Variables

All runtime settings are loaded via `maps4u.core.config.Settings` (environment variables override `.env` and `config/settings.yaml`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MAPS4U_DATA_DIR` | `./var` | Root directory for SQLite DB, audit logs, and corrections |
| `MAPS4U_DB_PATH` | `./var/maps4u.sqlite3` | SQLite WAL database file path |
| `MAPS4U_ARTIFACT_DIR` | `./var/jobs` | Directory storing per-job governed 5-artifact bundles |
| `MAPS4U_CACHE_DIR` | `./var/osm_cache` | Directory storing raw Overpass JSON and `.gpkg` snapshots |
| `MAPS4U_STYLE_DIR` | `./styles` | Root directory for versioned YAML cartographic styles |
| `MAPS4U_DEFAULT_STYLE` | `mcy/v1` | Default style reference (`styles/mcy/v1/style.yaml`) |
| `MAPS4U_MIN_FONT_MM` | `1.5` | Hard minimum printed font height floor (`mm`) |
| `MAPS4U_OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | Overpass API endpoint (supports `file://` for offline tests) |
| `MAPS4U_QUEUE` | `inline` | Execution mode: `inline` (synchronous) or `celery` (Redis worker) |
| `MAPS4U_REDIS_URL` | `redis://localhost:6379/0` | Redis broker/backend URL when `MAPS4U_QUEUE=celery` |
| `MAPS4U_RENDER_DPI` | `300` | Raster thumbnail resolution (`DPI`) |
| `MAPS4U_ENV` | `local` | Environment profile (`local`, `test`, `staging`, `prod`) |
| `MAPS4U_OPERATOR_TOKEN` | *(required in `prod`/`staging`)* | Operator Bearer token (`>= 16` chars, distinct from reviewer token) |
| `MAPS4U_REVIEWER_TOKEN` | *(required in `prod`/`staging`)* | Reviewer Bearer token for `/approve` & `/reject` (`>= 16` chars) |
| `MAPS4U_OPERATOR_IDENTITY` | `operator` | Immutable server-bound operator principal recorded in audit logs |
| `MAPS4U_REVIEWER_IDENTITY` | `reviewer` | Immutable server-bound reviewer principal recorded in `review_decisions` |

---

## 9. Testing, QA & Reproducibility Verification

All automated tests run 100% offline using recorded Overpass fixtures (`tests/fixtures/overpass/mcy_sample.json`):

```bash
# Run the full 95-test suite (unit, property-based, API, integration, 3-pilot acceptance, v1.0.1 & v1.0.2 hardening)
make test

# Run with line coverage report
make test-cov

# Run ruff linter and mypy strict type checks
make lint

# Execute online SQLite WAL + artifact backup/restore verification drill
python -m scripts.backup_restore_drill
```

---

## 10. Documentation & Governance Index

- **[Beginner's Step-by-Step Guide (`docs/getting-started-beginners.md`)](docs/getting-started-beginners.md)** — Zero-assumption walkthrough for downloading, starting, and using Maps4U.
- **[System Architecture (`docs/architecture.md`)](docs/architecture.md)** — Component topology, 11-stage state machine, SQLite WAL schema, and CRS design.
- **[HTTP API Reference (`docs/api.md`)](docs/api.md)** — Complete endpoint specifications, request/response payloads, and error codes.
- **[Operator Runbook (`docs/runbook.md`)](docs/runbook.md)** — Step-by-step map production, QA review, approval locking, and troubleshooting.
- **[Deployment & Backup Guide (`docs/deployment.md`)](docs/deployment.md)** — Docker Compose topology, volume layout, and backup/restore verification.
- **[Cartographic Style Guide (`docs/style-guide.md`)](docs/style-guide.md)** — Authoring and validating YAML style definitions (`styles/mcy/v1/style.yaml`).
- **[Client Corrections Guide (`docs/corrections-guide.md`)](docs/corrections-guide.md)** — Applying non-destructive `rename`, `reclass`, `add`, and `remove` YAML overrides.
- **[Testing & TDD Guide (`docs/testing.md`)](docs/testing.md)** — Test pyramid, Hypothesis invariants, golden determinism checks, and coverage.
- **[Pilot QA Acceptance Report (`docs/qa-acceptance.md`)](docs/qa-acceptance.md)** — Gate G5 multi-area verification across Maroochydore, Noosa, and Bribie Island.
- **[Threat Model (`docs/threat-model.md`)](docs/threat-model.md)** — Input validation bounds, Overpass fair-use protection, and runtime security controls.
- **[Owner Decision Register (`docs/decisions.md`)](docs/decisions.md)** — Decisions `OD-1` through `OD-9` and stage gate sign-offs.
- **[Architecture Decision Records (`docs/adr/`)](docs/adr/)** — `ADR-0001` through `ADR-0009`.
- **[Changelog (`CHANGELOG.md`)](CHANGELOG.md)** | **[Contributing (`CONTRIBUTING.md`)](CONTRIBUTING.md)** | **[Security (`SECURITY.md`)](SECURITY.md)** | **[Code of Conduct (`CODE_OF_CONDUCT.md`)](CODE_OF_CONDUCT.md)**

---

## 11. Acknowledgements & Special Thanks to Winston the Cat

A very special, heartfelt thank-you goes to **Winston the Cat** 🐾🐈 — Chief Feline Supervisor of Cartographic Quality — for his extraordinary patience, quiet supervision, and unwavering composure through every stage gate, late-night test run, label-collision algorithm, and PDF rendering verification that brought the **Maps4U Street Map System** to life.

> *"Every street corner mapped, every label aligned, and not a single keyboard walked across without good reason — thank you for your patience, Winston."* 🐱✨
