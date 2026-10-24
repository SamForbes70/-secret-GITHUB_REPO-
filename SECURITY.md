# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `1.0.x` (`v1.0.2`) | :white_check_mark: Supported |
| `< 1.0.0` | :x: Pre-release stages |

---

## Built-In Security Controls

1. **Geofence Input Bounds:** All GeoJSON polygons are validated for ring validity, vertex count (`<= 200` vertices/ring), multipolygon part count (`<= 3`), and metric UTM area (`<= 600.0 km²`) prior to Overpass query generation.
2. **Safe YAML Parsing & JSON Schema Validation:** All client correction files (`schemas/corrections.schema.json`) and cartographic styles (`schemas/style.schema.json`) are parsed exclusively via `yaml.safe_load` and validated against strict JSON Schemas.
3. **Artifact Path Whitelisting:** `GET /api/jobs/{job_id}/artifacts/{artifact_name}` strictly whitelists `GOVERNED_OUTPUT_FILES` (`proof.pdf`, `thumb.png`, `qa-report.md`, `qa-report.json`, `manifest.json`), preventing path traversal.
4. **Cryptographic Proof Integrity:** Every approved job locks its `proof_sha256` in SQLite (`review_decisions` and `bundles`) and `manifest.json`.
5. **Fail-Closed Production Authentication & RBAC (`SEC-001`, `SEC-002`, `SEC-003`):** Production and staging profiles (`MAPS4U_ENV=prod|staging`) refuse startup unless distinct `MAPS4U_OPERATOR_TOKEN` and `MAPS4U_REVIEWER_TOKEN` (`>= 16` characters, non-default) are configured. Header-only authentication (`Authorization: Bearer`, `X-Operator-Token`, `X-Reviewer-Token`) is enforced; query-string `?token=` authentication is rejected (`401`). Reviewer identities in `review_decisions` are bound strictly to server-configured principals (`MAPS4U_REVIEWER_IDENTITY`).
6. **Immutable Provenance & Tamper Detection (`DATA-001`, `DATA-002`, `BUG-015`):** OSM snapshots are content-addressed (`SHA-256(bbox+query+raw_sha256)`), exact job inputs are frozen in `frozen_inputs/`, and every artifact download verifies SHA-256 parity against `manifest.json` and `review_decisions.proof_sha256` (`409 E_STORAGE` on post-approval tampering).
7. **Secrets Hygiene:** No API keys, tokens, or credentials are stored in source control; `.env` is gitignored.

---

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues. Instead, contact the repository owner privately via GitHub security advisories with:
- A description of the issue and affected component (`src/maps4u/...`).
- Minimal reproduction steps.
- Potential impact assessment.
