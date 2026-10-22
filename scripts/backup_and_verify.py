"""Initialize git repo, run smoke test + QA suite, and create redundant backups."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path


def main() -> None:
    repo = Path(__file__).resolve().parents[1]

    # 1. Run smoke_test.py
    smoke = subprocess.run(
        ["/opt/venv/bin/python", "scripts/smoke_test.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if smoke.returncode != 0:
        raise RuntimeError(smoke.stderr)
    smoke_data = json.loads(smoke.stdout)

    # 2. Run ruff + mypy + pytest
    for cmd in (
        ["/opt/venv/bin/ruff", "check", "src", "tests", "scripts"],
        ["/opt/venv/bin/mypy", "src"],
        ["/opt/venv/bin/pytest", "-q"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)

    # 3. Git init + commit + tag
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)

    subprocess.run(["git", "config", "user.name", "Maps4U System"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "maps4u@local.dev"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if status:
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "feat(phase-0): Stage 1 scaffold, OSM fetch/cache, corrections, FastAPI routes, and smoke test (Gate G1)",
            ],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "tag", "-f", "v0.1.0-phase0"], cwd=repo, check=True)

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # 4. Redundant backups in /a0/usr/projects/maps4u/backups/ and /a0/usr/workdir/backups/maps4u/
    backup_dirs = [
        Path("/a0/usr/projects/maps4u/backups"),
        Path("/a0/usr/workdir/backups/maps4u"),
    ]
    artifacts_report: list[dict[str, object]] = []

    for bdir in backup_dirs:
        bdir.mkdir(parents=True, exist_ok=True)

    bare_repo = backup_dirs[0] / "maps4u-street-map-system.git"
    if not bare_repo.exists():
        subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True)

    remotes = subprocess.run(
        ["git", "remote"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if "backup" not in remotes:
        subprocess.run(["git", "remote", "add", "backup", str(bare_repo)], cwd=repo, check=True)

    subprocess.run(["git", "push", "--mirror", "backup"], cwd=repo, check=True)

    for bdir in backup_dirs:
        bundle_path = bdir / "maps4u-street-map-system-phase0.bundle"
        subprocess.run(["git", "bundle", "create", str(bundle_path), "--all"], cwd=repo, check=True)
        subprocess.run(["git", "bundle", "verify", str(bundle_path)], cwd=repo, check=True)

        tar_path = bdir / "maps4u-street-map-system-phase0.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(repo, arcname="maps4u-street-map-system")
            tf.add(
                "/a0/usr/workdir/maps4u-end-to-end-development-plan.md",
                arcname="docs/maps4u-end-to-end-development-plan.md",
            )
            tf.add(
                "/a0/usr/workdir/maps4u-machine-prd-v2.md",
                arcname="docs/maps4u-machine-prd-v2.md",
            )
            tf.add(
                "/a0/usr/workdir/maps4u-august-project-input.md",
                arcname="docs/maps4u-august-project-input.md",
            )
            tf.add(
                "/a0/usr/workdir/mission-checkpoints/maps4u/phase-0-stage-1-complete.json",
                arcname="checkpoints/phase-0-stage-1-complete.json",
            )

        for p in (bundle_path, tar_path):
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            (p.with_suffix(p.suffix + ".sha256")).write_text(f"{digest}  {p.name}\n", encoding="utf-8")
            artifacts_report.append(
                {
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "sha256": digest,
                }
            )

    print(
        json.dumps(
            {
                "git_head": head_sha,
                "git_tag": "v0.1.0-phase0",
                "bare_mirror": str(bare_repo),
                "smoke_test": smoke_data,
                "redundant_artifacts": artifacts_report,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
