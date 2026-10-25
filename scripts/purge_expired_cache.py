"""CLI utility to purge expired unreferenced OSM cache snapshots while preserving job-locked snapshots (R-14, OD-8)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from maps4u.core.config import Settings
from maps4u.geo.cache import purge_expired_unreferenced_snapshots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge expired unreferenced OSM cache snapshots while protecting all job-referenced snapshots."
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Override MAPS4U_CACHE_MAX_AGE_DAYS retention window (default: from settings, typically 30 days).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actual deletion on disk and SQLite (default is safe --dry-run mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and report purgable vs. protected snapshots without deleting anything (default).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Optional override for MAPS4U_DATA_DIR.",
    )
    parser.add_argument("--db-path", type=Path, default=None, help="Optional override for MAPS4U_DB_PATH.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Optional override for MAPS4U_CACHE_DIR.")
    parser.add_argument("--artifact-dir", type=Path, default=None, help="Optional override for MAPS4U_ARTIFACT_DIR.")
    args = parser.parse_args(argv)

    settings = Settings()
    if args.data_dir:
        data_dir = args.data_dir.resolve()
        default_db = data_dir / "maps4u.sqlite3"
        nested_db = data_dir / "db" / "maps4u.sqlite3"
        db_path = args.db_path or (nested_db if nested_db.is_file() and not default_db.is_file() else default_db)
        default_cache = data_dir / "osm_cache"
        nested_cache = data_dir / "cache" / "osm"
        cache_dir = args.cache_dir or (
            nested_cache if nested_cache.is_dir() and not default_cache.is_dir() else default_cache
        )
        artifact_dir = args.artifact_dir or (data_dir / "jobs")
    else:
        db_path = args.db_path or settings.db_path
        cache_dir = args.cache_dir or settings.cache_dir
        artifact_dir = args.artifact_dir or settings.artifact_dir

    max_age_days = args.max_age_days if args.max_age_days is not None else settings.maps4u_cache_max_age_days
    dry_run = not bool(args.execute)

    report = purge_expired_unreferenced_snapshots(
        db_path=db_path,
        cache_dir=cache_dir,
        artifact_dir=artifact_dir,
        max_age_days=max_age_days,
        dry_run=dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
