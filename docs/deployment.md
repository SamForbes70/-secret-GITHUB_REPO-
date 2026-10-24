# Maps4U Deployment, Operations, Security & Backup Guide (`v1.0.2`)

## 0. Production Secret Injection & Token Rotation (`SEC-001`, `SEC-002`, `SEC-003`)

In `prod` and `staging` environments (`MAPS4U_ENV=prod` or `staging`), `docker-compose.yml` and the FastAPI application factory (`create_app()`) **refuse startup** unless deployment-specific credentials are provided via environment variables or an untracked `.env` file:

```bash
export MAPS4U_OPERATOR_TOKEN="$(openssl rand -hex 24)"
export MAPS4U_REVIEWER_TOKEN="$(openssl rand -hex 24)"
export MAPS4U_OPERATOR_IDENTITY="ops.production"
export MAPS4U_REVIEWER_IDENTITY="qa.reviewer"
docker compose up -d --build
```

- **Minimum Strength & Separation of Duties:** Both tokens must be at least **16 characters**, must not match any known placeholder/default token (`maps4u-prod-operator-token`, `change-me`, etc.), and must be distinct (`MAPS4U_OPERATOR_TOKEN != MAPS4U_REVIEWER_TOKEN`).
- **Header-Only Authentication (`SEC-003`):** Tokens must be passed via `Authorization: Bearer <token>`, `X-Operator-Token`, or `X-Reviewer-Token` HTTP headers. Query-string `?token=` parameters are rejected (`401 E_UNAUTHORIZED`).
- **Token Rotation Procedure:**
  1. Generate new 48-hex-character secrets for `MAPS4U_OPERATOR_TOKEN` and/or `MAPS4U_REVIEWER_TOKEN` in your secret manager or `.env`.
  2. Recreate the `api` and `worker` containers (`docker compose up -d api worker`).
  3. Verify `/healthz` (`200`) and `/readyz` (`200`, `database: true`, `broker: true`, `worker: true`).
  4. Existing approved jobs and `review_decisions` remain intact because historical sign-offs store the verified principal identity (`MAPS4U_REVIEWER_IDENTITY`) and `proof_sha256`.

## 1. Container Topology (`docker-compose.yml`)

The production Docker Compose stack defines three services sharing a persistent `/var/maps4u` volume (`maps4u_data`):

| Service | Image / Build | Command / Role | Ports / Healthcheck |
| :--- | :--- | :--- | :--- |
| `redis` | `redis:7-alpine` | Message broker & Celery result backend | Internal `:6379` (`redis-cli ping`) |
| `api` | `Dockerfile` (`runtime` stage) | `uvicorn maps4u.api.main:create_app --factory --host 0.0.0.0 --port 8000` | Host `8000:8000` (`curl -fsS http://127.0.0.1:8000/healthz`) |
| `worker` | `Dockerfile` (`runtime` stage) | `celery -A maps4u.worker.tasks:celery_app worker --loglevel=INFO --concurrency=1` | Shares `maps4u_data` volume |

### Multi-Stage `Dockerfile` Design
1. **`builder` (`python:3.13-slim`):** Installs C/C++ geospatial build headers (`libgdal-dev`, `libgeos-dev`, `libproj-dev`) and compiles wheels into `/wheels`.
2. **`runtime` (`python:3.13-slim`):** Installs only minimal shared runtime libraries (`gdal-bin`, `libgeos-c1v5`, `libproj25`, `fonts-dejavu-core`, `sqlite3`, `curl`) and pre-built wheels.

---

## 2. Persistent Volume Layout (`/var/maps4u`)

```text
/var/maps4u/
├── maps4u.db                   # SQLite WAL database (+ .db-wal, .db-shm)
├── audit.jsonl                 # Append-only structured audit trail
├── corrections/                # Validated YAML correction files (corr-<sha>.yaml)
├── osm_cache/                  # Cached Overpass raw JSON + 8-layer .gpkg snapshots
└── jobs/
    └── <job_id>/
        ├── proof.pdf           # Print-ready vector PDF
        ├── thumb.png           # Raster preview thumbnail
        ├── qa-report.json      # Machine-readable QA preflight report
        ├── qa-report.md        # Human-readable QA preflight report
        ├── manifest.json       # Cryptographic SHA-256 provenance manifest
        └── drawlog.json        # Canonical vector draw-log
```

---

## 3. Online Backup & Restore Procedure

Because SQLite runs in `WAL` mode, file-level copies without checkpointing can miss uncommitted WAL frames. Always use `sqlite3.Connection.backup()` (implemented in `scripts/backup_restore_drill.py`):

```bash
# Run the automated online backup, restore, and SHA-256 verification drill
python -m scripts.backup_restore_drill
```

The drill verifies:
1. Online SQLite backup via `sqlite3.Connection.backup()` while the database is active.
2. Archive copy of all governed job bundles (`jobs/<job_id>/*`) and `.gpkg` caches.
3. Full restoration into a clean target directory and verification that:
   - `restored_ok == True`
   - `manifest_sha256_match == True`
   - `pdf_sha256_match == True`

### Repository & Artifact Backup Script
To create a full git bundle, `.tar.gz` archive, bare mirror update, and `.sha256` manifest:

```bash
python scripts/backup_and_verify.py
```
