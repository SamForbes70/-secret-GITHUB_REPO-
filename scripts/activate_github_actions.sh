#!/usr/bin/env bash
# Activate GitHub Actions workflow (.github/workflows/ci.yml) from deploy/github-actions-ci.yml
# Requires a GitHub token with the `workflow` OAuth scope (or `gh auth refresh -s workflow`).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p .github/workflows
cp deploy/github-actions-ci.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: activate GitHub Actions workflow (.github/workflows/ci.yml)" || true
git push origin main
echo "GitHub Actions workflow activated at .github/workflows/ci.yml"
