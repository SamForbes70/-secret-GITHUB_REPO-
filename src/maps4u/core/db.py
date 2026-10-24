"""SQLite connection and idempotent migration runner."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect_db(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _repair_legacy_geofence_revisions(conn: sqlite3.Connection) -> int:
    """Repair any legacy unscoped geofence_revisions rows (where revision_id == sha256(geometry_json)) (BUG-007)."""
    rows = conn.execute(
        "SELECT revision_id, project_id, geometry_json, created_at, created_by, is_current "
        "FROM geofence_revisions"
    ).fetchall()
    repaired = 0
    for row in rows:
        old_rev_id = str(row["revision_id"])
        proj_id = str(row["project_id"])
        geom_json = str(row["geometry_json"])
        geom_sha = hashlib.sha256(geom_json.encode("utf-8")).hexdigest()
        if old_rev_id != geom_sha:
            continue
        scoped_rev_id = hashlib.sha256(f"{proj_id}:{geom_sha}".encode()).hexdigest()
        conn.execute(
            """
            INSERT OR IGNORE INTO geofence_revisions (
                revision_id, project_id, geometry_json, created_at, created_by, is_current
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                scoped_rev_id,
                proj_id,
                geom_json,
                row["created_at"],
                row["created_by"],
                row["is_current"],
            ),
        )
        conn.execute(
            "UPDATE render_specifications SET geofence_revision = ? "
            "WHERE project_id = ? AND geofence_revision = ?",
            (scoped_rev_id, proj_id, old_rev_id),
        )
        conn.execute(
            "UPDATE jobs SET geofence_revision = ? "
            "WHERE project_id = ? AND geofence_revision = ?",
            (scoped_rev_id, proj_id, old_rev_id),
        )
        conn.execute(
            "DELETE FROM geofence_revisions WHERE revision_id = ? AND project_id = ?",
            (old_rev_id, proj_id),
        )
        repaired += 1
    return repaired


def run_migrations(db_path: Path) -> list[int]:
    """Apply all numbered SQL migrations in order idempotently and repair legacy revision keys."""
    applied_now: list[int] = []
    with db_session(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        existing = {
            int(row["version"])
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            match = re.match(r"^(\d+)_", sql_file.name)
            if not match:
                continue
            version = int(match.group(1))
            if version in existing:
                continue
            sql_text = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql_text)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
            applied_now.append(version)
        cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "retry_count" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        _repair_legacy_geofence_revisions(conn)
    return applied_now
