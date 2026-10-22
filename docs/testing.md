# MAPS4U Testing & TDD Policy (v0.1.0)

- **TDD First (C-3):** Every cartographic rule and data module begins with a failing test (RED), followed by minimal implementation (GREEN) and refactoring.
- **No Network in Automated Tests (§11.3):** All unit, integration, and API tests run offline using recorded Overpass fixtures (`MAPS4U_OVERPASS_URL=file://...`) and `MAPS4U_QUEUE=inline`.
- **Coverage Target:** >= 85% line coverage across `core`, `geo`, `render`, `labels`, `qa`.
