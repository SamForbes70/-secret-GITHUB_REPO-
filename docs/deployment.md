# Maps4U Deployment & Backup Guide (`S6.T1` & `S6.T2`)

## 1. Container Topology (`docker-compose.yml`)
- **`api`:** FastAPI + Uvicorn server on port `8000` with `/healthz` healthcheck.
- **`worker`:** Celery worker (`maps4u.worker.tasks:celery_app`) sharing `/var/maps4u` volume.
- **`redis`:** Redis 7 broker and result backend.
- **`maps4u_data` volume:** Mounted at `/var/maps4u`, storing `maps4u.db` (SQLite WAL), `cache/osm/` (`.gpkg` snapshots), `artifacts/` (governed job bundles), and `audit.jsonl`.

## 2. Backup & Restore Procedure
Run `python -m scripts.backup_restore_drill` to verify end-to-end online SQLite backup (`sqlite3.Connection.backup`) and artifact restore integrity (`manifest_sha256_match: true`, `pdf_sha256_match: true`).
