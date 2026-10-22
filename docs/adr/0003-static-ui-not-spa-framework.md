# ADR-0003: Vendored Static Leaflet UI for Pilot

- **Status:** Accepted
- **Context:** Operator needs a preview map with polygon drawing, paper selection, and viability feedback without a fragile JS build pipeline.
- **Decision:** Serve a static Leaflet + Leaflet-Draw operator UI from FastAPI.
