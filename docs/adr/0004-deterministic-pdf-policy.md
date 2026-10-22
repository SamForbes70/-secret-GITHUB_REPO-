# ADR-0004: Determinism Standard — Canonical Layout, Structure, and Normalized Hashes

- **Status:** Accepted
- **Context:** Raw PDF bytes can vary across native library builds unless normalized.
- **Decision:** Enforce deterministic feature ordering, seeded label placement, normalized PDF metadata, and golden tests against canonical draw-logs and PDF structural verification.
