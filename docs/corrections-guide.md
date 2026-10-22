# Maps4U Client Corrections Guide (`S6.T2`)

Client map corrections are stored in version-controlled YAML files validated against `schemas/corrections.schema.json` and applied non-destructively in memory on top of the cached OpenStreetMap GeoPackage snapshot.

## Supported Actions
1. **`rename`** — Change the display label of an existing OSM feature by `osm_id`.
2. **`reclass`** — Change the classification (`highway`, `water`, `landuse`, `place`) of an existing feature.
3. **`add`** — Insert a custom missing road (`LineString`) or landmark/place (`Point`) with WGS84 coordinates.
4. **`remove`** — Suppress a feature from rendering by `osm_id`.

## Example Corrections YAML
```yaml
corrections:
  - feature: road
    osm_id: 9002
    action: rename
    name: "First Ave Esplanade"
  - feature: landmark
    action: add
    name: "Surf Club Observation Deck"
    category: "community"
    geometry:
      type: Point
      coordinates: [153.098, -26.654]
```
