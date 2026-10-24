# Maps4U Client Corrections Guide (`v1.0.2`)

Client map corrections are stored in version-controlled YAML files validated against `schemas/corrections.schema.json` and applied non-destructively in memory (`src/maps4u/geo/corrections.py`) on top of the immutable OpenStreetMap GeoPackage (`.gpkg`) snapshot.

---

## 1. Core Design Principles

1. **Non-Destructive:** Raw Overpass responses and `.gpkg` caches are never mutated. Corrections are applied in memory during the `transforming` pipeline stage.
2. **Strict Schema Validation:** Every YAML file is parsed with `yaml.safe_load` and validated against `schemas/corrections.schema.json`. Invalid syntax, unknown actions, or missing required fields raise `E_CORRECTIONS_INVALID` (`422`).
3. **Cryptographic Provenance:** The SHA-256 digest of the corrections file is recorded in `corrections_files`, frozen into `render_specifications`, and emitted in the job's `manifest.json`.

---

## 2. Supported Target Features & Actions

### Target Feature Types (`feature`)
- `road` (maps to `roads` layer)
- `water` (maps to `water` / `water_lines` layers)
- `park` (maps to `parks` layer)
- `place` (maps to `places` layer)
- `landmark` (maps to `landmarks` layer)

### Supported Actions (`action`)

| Action | Required Fields | Behavior |
| :--- | :--- | :--- |
| `rename` | `feature`, `osm_id`, `name` | Replaces the display label of the matching `osm_id` feature. |
| `reclass` | `feature`, `osm_id`, `new_class` | Updates the classification (`highway`, `water`, `landuse`, `place`) of the matching `osm_id` feature. |
| `add` | `feature`, `name`, `geometry` (optional `category`, `highway`, `osm_id`) | Appends a new WGS84 `Point` or `LineString` feature to the target layer. |
| `remove` | `feature`, `osm_id` | Suppresses the matching `osm_id` feature from rendering and street indexing. |

---

## 3. Complete Example Corrections YAML

```yaml
corrections:
  # 1. Rename an existing street by OSM ID
  - feature: road
    osm_id: 9002
    action: rename
    name: "First Ave Esplanade"

  # 2. Reclassify a road from tertiary to secondary
  - feature: road
    osm_id: 9003
    action: reclass
    new_class: "secondary"

  # 3. Add a custom local landmark POI
  - feature: landmark
    action: add
    name: "Maroochydore Surf Club Observation Deck"
    category: "community"
    geometry:
      type: Point
      coordinates: [153.098, -26.654]

  # 4. Suppress a private service road from the map
  - feature: road
    osm_id: 9006
    action: remove
```

---

## 4. Submitting Corrections via HTTP API

Submit `yaml_content` and `author` to `POST /api/jobs/{job_id}/corrections`. This validates the YAML, persists it to `<MAPS4U_DATA_DIR>/corrections/`, and returns a new child `JobResponse` in state `created`. Execute `POST /api/jobs/{child_job_id}/run` to generate the updated proof bundle.
