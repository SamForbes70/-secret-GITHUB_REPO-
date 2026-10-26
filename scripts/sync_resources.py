# ruff: noqa: E501
"""Synchronize or verify parity between repo-level config/styles/schemas and src/maps4u/resources/."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RESOURCE_PAIRS: tuple[tuple[str, str], ...] = (
    ("config/logging.yaml", "src/maps4u/resources/config/logging.yaml"),
    ("config/paper_templates.yaml", "src/maps4u/resources/config/paper_templates.yaml"),
    ("config/settings.yaml", "src/maps4u/resources/config/settings.yaml"),
    ("styles/mcy/v1/style.yaml", "src/maps4u/resources/styles/mcy/v1/style.yaml"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_or_check(*, check_only: bool = False) -> dict[str, object]:
    synced: list[str] = []
    drifted: list[str] = []
    for src_rel, dst_rel in RESOURCE_PAIRS:
        src = REPO_ROOT / src_rel
        dst = REPO_ROOT / dst_rel
        if not src.is_file():
            drifted.append(f"missing_source:{src_rel}")
            continue
        if not dst.is_file() or _sha256(src) != _sha256(dst):
            if check_only:
                drifted.append(src_rel)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                synced.append(src_rel)
    return {
        "check_only": check_only,
        "in_sync": len(drifted) == 0,
        "synced": synced,
        "drifted": drifted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync or verify repo config/styles with bundled package resources.")
    parser.add_argument("--check", action="store_true", help="Check parity without modifying files (exit 1 on drift).")
    args = parser.parse_args(argv)
    report = sync_or_check(check_only=bool(args.check))
    print(json.dumps(report, indent=2))
    return 0 if report["in_sync"] else 1


if __name__ == "__main__":
    sys.exit(main())
