#!/usr/bin/env bash
# v1.0.5 GitHub Actions are stored directly under .github/workflows/.
# This compatibility helper deliberately does not commit or push to main.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "${REPO_ROOT}/.github/workflows/ci.yml"
test -f "${REPO_ROOT}/.github/workflows/e2e.yml"
echo "CI and end-to-end workflows are present. Review the PR checks before merging."
