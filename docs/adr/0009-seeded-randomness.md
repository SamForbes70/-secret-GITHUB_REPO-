# ADR-0009: Zero Unseeded Randomness in Cartographic Pipeline

- **Status:** Accepted (Stage 4 Gate `G4`)
- **Date:** 2026-10-22
- **Owners:** MAPS4U Engineering

## Context
Nondeterministic set iteration or unseeded tie-breaking during label collision resolution causes labels to shift between runs.

## Decision
1. Freeze `"seed": 0` in every canonical `RenderSpec`.
2. Order all label candidates deterministically by `(priority_rank, -length_m, osm_id, text)` before `STRtree` collision checks (`src/maps4u/labels/engine.py`).

## Verification
- `tests/unit/test_stage4_labels_and_furniture.py`
