# ADR-0002: Dual Storage Profile — SQLite WAL + GeoPackage for Pilot, PostgreSQL/PostGIS + S3 for Stage 7

- **Status:** Accepted (Stage 1 Gate `G1` / Stage 6 Gate `G6`)
- **Date:** 2026-10-21
- **Owners:** MAPS4U Engineering

## Context
The pilot deployment targets a single-operator local Docker or workstation environment where running and maintaining a dedicated PostgreSQL/PostGIS cluster adds unnecessary operational overhead, while Stage 7 cloud multi-operator deployment requires centralized PostGIS and S3 object storage.

## Decision
1. Use SQLite in `WAL` mode (`PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;`) for all relational state and audit tables (`src/maps4u/core/migrations/0001_initial.sql`).
2. Store normalized 8-layer OpenStreetMap extracts (`roads`, `water`, `water_lines`, `parks`, `boundaries`, `coastline`, `places`, `landmarks`) as immutable GeoPackage (`.gpkg`) snapshots keyed by SHA-256 on the local filesystem.
3. Ensure online backup safety via `sqlite3.Connection.backup()` paired with artifact tarball verification (`scripts/backup_restore_drill.py`).

## Verification
- `tests/unit/test_state_and_db.py` & `tests/integration/test_acquire.py`
- `tests/integration/test_stage6_packaging_and_handover.py` (`test_s6_t2_handover_docs_and_backup_restore_drill`)
