# Contributing to Maps4U Street Map System

Thank you for contributing to the **Maps4U Street Map System** (`maps4u-maps`)! To keep the cartographic pipeline 100% deterministic, offline-testable, and config-driven, all contributions must follow the engineering standards below.

---

## 1. Core Engineering Rules

1. **Strict TDD First (`C-3`):**
   - Every new feature, cartographic rule, or bug fix must begin with a failing unit, property-based, or integration test (`RED`), followed by the minimal implementation (`GREEN`) and cleanup (`REFACTOR`).
2. **Cartographic Rules Live in YAML Config (`C-2`):**
   - Never hardcode hex colours, stroke widths, font families, font sizes (`mm`), or scale-band thresholds in Python code. All visual rules belong in `styles/<style_id>/<version>/style.yaml` (validated by `schemas/style.schema.json`) and `config/paper_templates.yaml`.
3. **100% Deterministic Output (`C-4`):**
   - Never introduce unseeded randomness, wall-clock timestamps inside PDF streams, or unsorted set iteration. Repeated renders of identical inputs must produce byte-identical `proof.pdf` SHA-256 hashes.
4. **Zero External Network Calls in Automated Tests:**
   - Unit, API, and integration tests must run offline using `MAPS4U_OVERPASS_URL=file://...` fixtures under `tests/fixtures/` and `MAPS4U_QUEUE=inline`.
5. **MVP Scope Lock (`C-1`):**
   - Do not introduce advertising slots, QR code generators, M2G/DDD integrations, Google Business Profile sync, or self-service public portals.

---

## 2. Local Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

---

## 3. Pre-Commit Verification Checklist

Before opening a Pull Request, run all verification gates locally:

```bash
# 1. Lint and format check
ruff check src tests

# 2. Static type checking
mypy src/maps4u/core src/maps4u/geo

# 3. Full offline test suite (must pass 100%)
MAPS4U_QUEUE=inline pytest -m "not live"

# 4. Online SQLite WAL + artifact backup/restore drill
python -m scripts.backup_restore_drill
```

---

## 4. Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat(render): ...`
- `fix(labels): ...`
- `docs(readme): ...`
- `test(qa): ...`
- `chore(docker): ...`
