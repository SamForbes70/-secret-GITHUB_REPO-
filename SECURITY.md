# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `1.0.x` (`v1.0.0-mvp`) | :white_check_mark: Supported |
| `< 1.0.0` | :x: Pre-release stages |

---

## Built-In Security Controls

1. **Geofence Input Bounds:** All GeoJSON polygons are validated for ring validity, vertex count (`<= 200` vertices/ring), multipolygon part count (`<= 3`), and metric UTM area (`<= 600.0 km²`) prior to Overpass query generation.
2. **Safe YAML Parsing & JSON Schema Validation:** All client correction files (`schemas/corrections.schema.json`) and cartographic styles (`schemas/style.schema.json`) are parsed exclusively via `yaml.safe_load` and validated against strict JSON Schemas.
3. **Artifact Path Whitelisting:** `GET /api/jobs/{job_id}/artifacts/{artifact_name}` strictly whitelists `GOVERNED_OUTPUT_FILES` (`proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, `manifest.json`), preventing path traversal.
4. **Cryptographic Proof Integrity:** Every approved job locks its `proof_sha256` in SQLite (`review_decisions` and `bundles`) and `manifest.json`.
5. **Secrets Hygiene:** No API keys, tokens, or credentials are stored in source control; `.env` is gitignored.

---

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues. Instead, contact the repository owner privately via GitHub security advisories with:
- A description of the issue and affected component (`src/maps4u/...`).
- Minimal reproduction steps.
- Potential impact assessment.
