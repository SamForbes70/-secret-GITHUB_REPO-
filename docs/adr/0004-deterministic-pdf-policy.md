# ADR-0004: Determinism Standard — Byte-Identical Vector PDF & Canonical Draw-Log

- **Status:** Accepted (Stage 3 Gate `G3` / Stage 5 Gate `G5`)
- **Date:** 2026-10-22
- **Owners:** MAPS4U Engineering

## Context
Standard PDF generators embed wall-clock timestamps (`/CreationDate`, `/ModDate`) and random document `/ID` tokens, causing identical map inputs to produce different SHA-256 hashes on repeat runs.

## Decision
1. Sort all spatial features deterministically by `(z_order, feature_class, osm_id)` prior to styling and label placement.
2. Normalize PDF stream headers, font descriptors, and metadata inside `CairoCanvas` (`src/maps4u/render/cairo_canvas.py`) so that identical inputs emit **byte-for-byte identical `proof.pdf` files** (`pdf_sha256`) and identical `content_hash()` draw logs.
3. Verify reproducibility via `maps4u.bundle.archive.reproduce(job_id)`.

## Verification
- `tests/unit/test_stage3_canvas_and_style.py`
- `tests/integration/test_stage5_reproducibility_and_pilots.py`
