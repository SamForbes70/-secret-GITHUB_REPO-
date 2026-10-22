# ADR-0005: Overpass Fair-Use, Raw-Bytes Provenance, and Offline Fixture Mode

- **Status:** Accepted
- **Context:** OSM extraction must respect public Overpass fair-use limits and remain 100% offline-testable.
- **Decision:** Max concurrency 1, sequential class-group queries, retry backoff (10/30/90s), store raw Overpass response bytes before parsing, and support `file://` recorded fixtures in tests.
