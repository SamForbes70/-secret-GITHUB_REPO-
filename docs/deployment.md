# Maps4U Deployment, Operations & Backup Guide (`v1.0.0-mvp`)

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
