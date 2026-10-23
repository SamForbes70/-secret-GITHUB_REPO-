## Summary
Describe what this PR changes and which Stage/Gate or ADR it addresses.

## Pre-Merge Verification Checklist
- [ ] Written TDD-first with offline tests (`MAPS4U_QUEUE=inline pytest -m "not live"` passes 100%).
- [ ] Zero hardcoded cartographic colours, widths, or font sizes in Python (`styles/mcy/v1/style.yaml` only).
- [ ] Deterministic output verified (`reproduce()` and `pdf_sha256` match across repeat runs).
- [ ] `ruff check src tests` and `mypy src/maps4u/core src/maps4u/geo` pass with zero errors.
- [ ] Documentation updated (`README.md`, `docs/`, `CHANGELOG.md`).
- [ ] Approved by **Winston the Cat** 🐾
