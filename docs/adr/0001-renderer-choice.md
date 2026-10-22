# ADR-0001: Renderer Choice — Deterministic Vector PDF & Thumbnail Engine (`CairoCanvas`)

- **Status:** Accepted (Stage 3 Gate `G3`)
- **Date:** 2026-10-22
- **Owners:** MAPS4U Engineering

## Context
`MAPS4U-PLAN-001` (§5.1, §9 ADR-1, and Stage 3 `S3.T1`) requires a vector PDF renderer behind the `Canvas` protocol (`src/maps4u/render/canvas.py`) that emits 100% vector geometry (`m`, `l`, `h`, `S`, `f`, `B`, `d`, `w`, `RG`, `rg`), embedded TrueType font descriptors, exact `MediaBox`/`TrimBox`/`BleedBox`, byte-identical `proof.pdf` (`pdf_sha256`) and `content_hash()` across repeated runs, and a raster `thumb.png`.

## Decision
We implemented `CairoCanvas` (`src/maps4u/render/cairo_canvas.py`) as the canonical `Canvas` implementation, emitting deterministic PDF 1.4 vector streams directly alongside `drawlog.json` and rendering PNG thumbnails via `Pillow`.

## Verification Results
- `tests/unit/test_stage3_canvas_and_style.py`: Verified byte-for-byte identical `proof.pdf` and identical `content_hash()` across repeated runs.
- `tests/integration/test_stage3_proof_render.py`: Verified Maroochydore A4 landscape proof render (`page_count == 1`, `page_size_matches == True`, `has_vector_paths == True`, `fonts_embedded == True`, `has_odbl_attribution == True`, `has_unexpected_raster == False`).
