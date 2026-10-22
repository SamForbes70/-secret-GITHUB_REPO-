# ADR-0002: Dual Storage Profile — SQLite + GeoPackage for Pilot, PostgreSQL/PostGIS + S3 for Stage 7

- **Status:** Accepted
- **Context:** Pilot runs locally for a single operator; production hardening is gated on a separate owner decision (Stage 7).
- **Decision:** Use SQLite (`WAL` mode) for state/audit and GeoPackage (`.gpkg`) snapshots on local filesystem for the pilot, keeping column semantics identical to the Stage 7 PostgreSQL/PostGIS schema.
