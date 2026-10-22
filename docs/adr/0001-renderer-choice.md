# ADR-0001: Renderer Choice — Pycairo Vector Canvas Primary, Mapnik Spike, ReportLab Fallback

- **Status:** Accepted (Baseline Sept 2026)
- **Context:** Maps4U requires deterministic vector PDF street maps with selectable text and exact typographic measurement.
- **Decision:** Implement a renderer-agnostic `Canvas` protocol (`src/maps4u/render/canvas.py`) with a canonical JSON draw-log. Use Pycairo (`cairo_canvas.py`) as the primary v1 vector PDF/SVG renderer, run an empirical comparison spike against Mapnik in Stage 3, and retain ReportLab as fallback.
