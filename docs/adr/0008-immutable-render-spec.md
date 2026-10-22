# ADR-0008: Immutable Geofence Revisions and Frozen Render Specifications

- **Status:** Accepted
- **Context:** Auditing and reproducibility require that any change after proof generation triggers a new render and review cycle.
- **Decision:** Geofence edits create immutable `geofence_revisions`; job creation freezes a `render_specifications` record hashed by canonical JSON.
