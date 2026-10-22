# Maps4U Operator Runbook (`S6.T2`)

## 1. Starting the System
Run `docker compose up -d --build` (or `make run`). Verify service health at `http://localhost:8000/healthz` and `http://localhost:8000/readyz`.

## 2. Step-by-Step Map Production Workflow
1. **Create a Project:** Open `http://localhost:8000/` or `POST /api/projects` with `{"area_name": "Maroochydore"}`.
2. **Draw Geofence & Check Viability:** Draw the polygon on the Leaflet map (or load the Maroochydore preset), choose `A3`/`A4`/`A5` and `landscape`/`portrait`, and review the live scale denominator (`1:N`) and minimum font height (`>= 1.5 mm`).
3. **Save Geofence Revision & Create Job:** Click **Save Geofence & Create Job** (`POST /api/projects/{id}/geofence` followed by `POST /api/jobs`).
4. **Execute Render Pipeline:** Trigger `POST /api/jobs/{job_id}/run`. The worker executes all 11 governed stages (`validating` through `proof_ready`).
5. **Inspect Governed Proof Bundle:** Download `proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, and `manifest.json` from `/api/jobs/{job_id}/artifacts/{name}`.
6. **Approve or Reject:**
   - To approve for print: `POST /api/jobs/{job_id}/approve` with `{"reviewer": "name", "comment": "Approved"}`. This locks `proof_sha256` in `review_decisions`.
   - To reject: `POST /api/jobs/{job_id}/reject` with a mandatory non-blank `comment` (`422` if blank).
7. **Apply Client Corrections:** Submit YAML corrections via `POST /api/jobs/{job_id}/corrections` to spawn a new child job while keeping the parent job and cached `.gpkg` immutable.
