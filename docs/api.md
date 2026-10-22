# Maps4U HTTP API Reference (`S6.T2`)

## System & Discovery
- `GET /healthz` — Liveness probe (`{"status": "ok"}`).
- `GET /readyz` — Readiness probe verifying SQLite WAL and artifact directory write access.
- `GET /api/meta` — Version, available styles, paper formats (`A3`, `A4`, `A5`), orientations, and legibility thresholds.
- `GET /api/templates` — Resolved geometry for all 6 paper/orientation templates.
- `GET /api/styles` & `GET /api/styles/{style_id}/{version}` — Cartographic style metadata and SHA-256.

## Projects, Geofences & Viability
- `POST /api/projects` / `GET /api/projects/{project_id}` — Create and inspect map projects.
- `POST /api/projects/{project_id}/geofence` / `GET /api/projects/{project_id}/revisions` — Save and list immutable WGS84 geofence revisions.
- `POST /api/viability` — Compute print scale (`1:N`), minimum printed font height (`mm`), label density ratio, warnings, blockers, and remediation choices.

## Jobs, Governed Artifacts & Review Decisions
- `POST /api/jobs` / `GET /api/jobs` / `GET /api/jobs/{job_id}` — Create and inspect frozen render jobs.
- `POST /api/jobs/{job_id}/run` — Execute the 11-stage governed pipeline to `proof_ready`.
- `GET /api/jobs/{job_id}/artifacts/{artifact_name}` — Download `proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, or `manifest.json`.
- `POST /api/jobs/{job_id}/approve` — Lock `proof_sha256` in `review_decisions` and transition to `finalized`.
- `POST /api/jobs/{job_id}/reject` — Require non-blank comment (`422` if blank) and transition to `rejected`.
- `POST /api/jobs/{job_id}/corrections` — Validate YAML corrections and create a child job.
