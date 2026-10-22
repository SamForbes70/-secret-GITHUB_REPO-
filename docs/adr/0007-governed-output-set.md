# ADR-0007: Governed Four-Artefact Output Set

- **Status:** Accepted
- **Context:** No proof may be reviewed without its supporting QA report, preview thumbnail, and provenance manifest.
- **Decision:** Server state machine enforces that `proof.pdf`, `thumb.png`, `qa-report.md`/`qa-report.json`, and `manifest.json` all exist before transitioning a job to `proof_ready`.
