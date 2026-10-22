# MAPS4U Threat Model Note (v0.1.0 — Stage 0 Baseline)

1. **Untrusted Geometry / Upload Inputs:** Mitigated via strict Pydantic validation, polygon vertex/area caps (<=200 vertices/ring, <=600 km²), and `yaml.safe_load` with JSON Schema validation on corrections files (<=1 MB).
2. **External Provider Availability (Overpass):** Mitigated via concurrency=1, retry/backoff ladder, raw-bytes caching, and deterministic snapshot reuse.
3. **Secret Leakage:** No secrets in repository; `.env` gitignored; structured logging redacts sensitive fields.
4. **Unreviewed AI Decisions:** Zero AI components in the runtime cartographic pipeline.
