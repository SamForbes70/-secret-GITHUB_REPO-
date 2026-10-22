# MAPS4U System Architecture (v0.1.0)

 Containerised pipeline-orchestrator architecture with two profiles:
- **Pilot profile:** FastAPI + Celery/Redis (or `MAPS4U_QUEUE=inline` in dev/test) + SQLite (`WAL`) + GeoPackage (`.gpkg`) cache + local filesystem artifacts.
- **Production profile (Stage 7, gated):** PostgreSQL/PostGIS + S3-compatible object store + OIDC.

See `docs/development-plan.md` §2–§7 and `docs/adr/0001..0009` for binding contracts.
