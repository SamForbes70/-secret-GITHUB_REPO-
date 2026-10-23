# Maps4U HTTP API Reference (`v1.0.0-mvp`)

All HTTP endpoints are served by the FastAPI application (`maps4u.api.main:app` / `create_app`). Domain errors return structured JSON envelopes via `Maps4UError`.

---

## 1. Error Envelope & Canonical Error Codes

All domain errors return:

```json
{
  "error": {
    "code": "E_GEO_INVALID",
    "message": "Human-readable explanation",
    "details": {}
  }
}
```

| Error Code | Default HTTP Status | Meaning |
| :--- | :--- | :--- |
| `E_GEO_INVALID` | `422` | Invalid GeoJSON geometry, self-intersecting polygon, or coordinates outside WGS84 bounds. |
| `E_GEO_TOO_LARGE` | `422` | Geofence exceeds `max_geofence_area_km2` (`600 km²`), `max_ring_vertices` (`200`), or `max_multipolygon_parts` (`3`). |
| `E_GEO_UNSUPPORTED` | `422` | Geometry type is not `Polygon` or `MultiPolygon`. |
| `E_OVERPASS_UNAVAILABLE` | `503` / `422` | Upstream Overpass API failed after full retry/backoff ladder. |
| `E_CORRECTIONS_INVALID` | `422` | Client corrections YAML failed schema validation or rejection comment was blank. |
| `E_STYLE_INVALID` | `422` | Style YAML failed `schemas/style.schema.json` validation. |
| `E_STATE_ILLEGAL` | `409` | Requested job state transition violates `LEGAL_TRANSITIONS`. |
| `E_GOVERNED_OUTPUT_MISSING` | `409` | Attempted transition to `proof_ready` when one or more governed output files are missing or empty. |
| `E_NOT_FOUND` | `404` | Requested project, geofence revision, job, or artifact does not exist. |
| `E_STORAGE` | `500` | Filesystem or SQLite persistence failure. |

---

## 2. System, Health & Discovery Endpoints

### `GET /healthz`
Liveness probe.

- **Response (`200 OK`):**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

### `GET /readyz`
Readiness probe verifying SQLite WAL connectivity and configured queue mode.

- **Response (`200 OK`):**
```json
{
  "ready": true,
  "queue_mode": "inline"
}
```

### `GET /api/meta`
Returns system version, registered style references, supported paper sizes, orientations, and minimum font legibility threshold.

- **Response (`200 OK`):**
```json
{
  "version": "1.0.0",
  "style_refs": ["mcy/v1"],
  "papers": ["A3", "A4", "A5"],
  "orientations": ["landscape", "portrait"],
  "thresholds": {
    "min_font_mm": 1.5
  }
}
```

### `GET /api/templates`
Returns resolved physical sheet geometry (`page_mm`, `bleed_mm`, `margins_mm`, `map_area_mm`, `furniture`, `grid`) for all 6 paper/orientation combinations (`A3-landscape`, `A3-portrait`, `A4-landscape`, `A4-portrait`, `A5-landscape`, `A5-portrait`).

### `GET /api/styles`
Lists registered cartographic styles and their SHA-256 digests.

- **Response (`200 OK`):**
```json
[
  {
    "style_ref": "mcy/v1",
    "style_version": "1.0.0",
    "approved": false,
    "derived_from": "MCY-reference.pdf (Maroochydore Street Map Baseline)",
    "sha256": "...",
    "scale_bands": ["detail", "standard_street", "overview"]
  }
]
```

---

## 3. Projects & Immutable Geofence Revisions

### `POST /api/projects`
Creates a new map project.

- **Request Body:**
```json
{
  "area_name": "Maroochydore",
  "reference": "MCY-2026",
  "notes": "Sunshine Coast pilot sheet"
}
```
- **Response (`201 Created`):** `ProjectResponse` containing `project_id`, `area_name`, `created_at`, `reference`, `notes`.

### `GET /api/projects` & `GET /api/projects/{project_id}`
Lists all projects or retrieves a single project including its `current_geofence` revision and associated `jobs`.

### `POST /api/projects/{project_id}/geofence`
Validates, canonicalises (6-decimal WGS84 coordinate rounding, CCW exterior ring), and stores an immutable geofence revision, marking it `is_current = 1`.

- **Request Body:**
```json
{
  "type": "Polygon",
  "coordinates": [[[
    [153.085, -26.660],
    [153.105, -26.660],
    [153.105, -26.645],
    [153.085, -26.645],
    [153.085, -26.660]
  ]]],
  "created_by": "operator"
}
```
- **Response (`201 Created`):** `GeofenceRevisionResponse` (`revision_id`, `project_id`, `is_current`, `created_at`, `geometry`).

### `GET /api/projects/{project_id}/revisions`
Lists all historical geofence revisions for `project_id` ordered newest-first.

---

## 4. Print Scale & Font Legibility Viability

### `POST /api/viability`
Projects the WGS84 geofence to its centroid UTM zone, computes natural and snapped print scales (`1:N`) against the chosen paper template's `map_area_mm`, and evaluates whether all mandatory label classes meet the **1.5 mm** minimum printed font height.

- **Request Body:**
```json
{
  "geofence": {
    "type": "Polygon",
    "coordinates": [[[
      [153.085, -26.660], [153.105, -26.660],
      [153.105, -26.645], [153.085, -26.645],
      [153.085, -26.660]
    ]]]
  },
  "paper": "A4",
  "orientation": "landscape",
  "style_ref": "mcy/v1"
}
```
- **Response (`200 OK`):**
```json
{
  "viable": true,
  "scale_denominator": 12500.0,
  "natural_scale_denominator": 11420.5,
  "scale_band": "standard_street",
  "min_font_mm": 1.5,
  "min_font_threshold_mm": 1.5,
  "packing_ratio": 0.42,
  "warnings": [],
  "blockers": [],
  "remediations": []
}
```

---

## 5. Jobs, Governed Artifacts & Review Decisions

### `POST /api/jobs`
Freezes a canonical `RenderSpec` (`spec_id`) and creates a job in state `created`.

- **Request Body:**
```json
{
  "project_id": "proj-...",
  "geofence_revision": "rev-...",
  "paper": "A4",
  "orientation": "landscape",
  "edition": "2026-10",
  "style_ref": "mcy/v1",
  "corrections_ref": null
}
```
- **Response (`201 Created`):** `JobResponse` (`job_id`, `spec_id`, `status: "created"`, etc.).

### `GET /api/jobs` & `GET /api/jobs/{job_id}`
Lists jobs (optional `?status_filter=proof_ready&limit=50`) or fetches a single job.

### `POST /api/jobs/{job_id}/run`
Executes the 11-stage governed pipeline (`created` → `...` → `proof_ready`) and returns the updated `JobResponse`.

### `GET /api/jobs/{job_id}/artifacts/{artifact_name}`
Downloads one of the 5 governed artifacts for `job_id`:
- `proof.pdf` (`application/pdf`)
- `thumb.png` (`image/png`)
- `qa-report.md` (`text/markdown`)
- `qa-report.json` (`application/json`)
- `manifest.json` (`application/json`)

### `POST /api/jobs/{job_id}/approve`
Cryptographically hashes `proof.pdf` (`proof_sha256`), records an `approved` entry in `review_decisions`, and transitions the job from `proof_ready` to `finalized`.

- **Request Body:** `{"reviewer": "operator", "comment": "Approved for print."}`

### `POST /api/jobs/{job_id}/reject`
Requires a non-blank `comment` (`422 E_CORRECTIONS_INVALID` if blank), records a `rejected` entry in `review_decisions`, and transitions the job from `proof_ready` to `rejected`.

- **Request Body:** `{"reviewer": "operator", "comment": "Rename First Avenue to First Ave Esplanade."}`

### `POST /api/jobs/{job_id}/corrections`
Validates `yaml_content` against `schemas/corrections.schema.json`, persists the immutable correction file under `<MAPS4U_DATA_DIR>/corrections/`, and spawns a new child job in state `created`.

- **Request Body:**
```json
{
  "yaml_content": "corrections:\n  - feature: road\n    osm_id: 9002\n    action: rename\n    name: 'First Ave Esplanade'\n",
  "author": "operator"
}
```

### `POST /api/jobs/{job_id}/retry`
Transitions a `failed` job back to `queued` so it can be re-executed.
