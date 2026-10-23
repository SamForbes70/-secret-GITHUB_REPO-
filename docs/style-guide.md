# Maps4U Cartographic Style Authoring Guide (`styles/mcy/v1/style.yaml`)

All cartographic styling rules live in declarative YAML (`styles/mcy/v1/style.yaml`) and are validated at load time against `schemas/style.schema.json`. Zero colours, line widths, or font sizes are hardcoded in Python (`src/maps4u/render/style_engine.py`).

---

## 1. Top-Level Sections of `style.yaml`

| Section | Purpose |
| :--- | :--- |
| `style_version` | Semantic version of the style schema (`"1.0.0"`). |
| `meta` | `style_ref` (`mcy/v1`), `derived_from`, `approved` boolean, and editorial `notes`. |
| `fonts` | Typography definitions (`family`, `weight`, `size_mm`, optional `spacing_mm`, optional `halo` with `color` & `width_mm`) for `suburb`, `landmark`, `arterial`, `collector`, `local`, and `service`. |
| `label_rules` | Deterministic placement parameters: `priority_order`, `candidate_order`, `repeat_every_mm` (`120.0`), `max_repeats` (`3`), `min_font_mm` (`1.5`), and `packing_factor` (`1.8`). |
| `layers` | Visual styling and integer `z`-order for `background`, `water`, `parks`, `water_lines`, `coastline`, `roads` (per highway class), and `boundaries`. |
| `scale_bands` | Scale-dependent feature filtering and Douglas-Peucker simplification tolerances (`detail`, `standard_street`, `overview`). |

---

## 2. Typography & Minimum Font Legibility (`fonts` & `label_rules`)

Every font class specifies its physical printed cap height in millimetres (`size_mm`). Both `assess()` and `run_qa()` reject any style or scale where a placed label falls below `min_font_mm` (`1.5 mm`):

| Font Class | Font Family | Size (`mm`) | Halo (`mm`) | Feature Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `suburb` | `DejaVuSans-Bold` | `4.5` | `0.6` (`#ffffff`) | `places` (`suburb`, `town`, `locality`) |
| `landmark` | `DejaVuSans-Bold` | `2.8` | `0.4` (`#ffffff`) | `landmarks`, `parks`, `water` polygons |
| `arterial` | `DejaVuSans-Bold` | `2.6` | `0.4` (`#ffffff`) | `motorway`, `trunk`, `primary`, `secondary` |
| `collector` | `DejaVuSans` | `2.1` | `0.3` (`#ffffff`) | `tertiary` |
| `local` | `DejaVuSans` | `1.8` | — | `residential`, `unclassified` |
| `service` | `DejaVuSans` | `1.5` | — | `service`, `track` |

---

## 3. Road Hierarchy & Two-Pass Casing/Fill Rendering (`layers.roads`)

Roads are rendered in two passes per road class — outer casing stroke first, inner fill stroke second — ordered monotonically by `z`:

| Highway Class | Casing Color / Width (`mm`) | Fill Color / Width (`mm`) | Z-Order |
| :--- | :--- | :--- | :--- |
| `motorway` | `#3d3d3d` / `1.80` | `#ffd54f` / `1.30` | `22` |
| `trunk` | `#454545` / `1.50` | `#ffe082` / `1.10` | `20` |
| `primary` | `#4a4a4a` / `1.30` | `#fff59d` / `0.95` | `18` |
| `secondary` | `#555555` / `1.10` | `#ffffff` / `0.80` | `16` |
| `tertiary` | `#666666` / `0.95` | `#ffffff` / `0.68` | `14` |
| `residential` | `#777777` / `0.75` | `#ffffff` / `0.52` | `12` |
| `unclassified` | `#777777` / `0.70` | `#ffffff` / `0.48` | `11` |
| `service` | `#888888` / `0.50` | `#f5f5f5` / `0.32` | `10` |
| `track` | `#999999` / `0.40` | `#eeeeee` / `0.25` | `9` |

---

## 4. Scale Bands (`scale_bands`)

| Scale Band | Max Scale Denominator | Simplification Tolerance (`m`) | Included Road Classes |
| :--- | :--- | :--- | :--- |
| `detail` | `<= 1:8,000` | `0.5 m` | All classes (`motorway` through `track`) |
| `standard_street` | `<= 1:20,000` | `1.5 m` | `motorway` through `unclassified` |
| `overview` | `<= 1:50,000` | `5.0 m` | `motorway`, `trunk`, `primary`, `secondary`, `tertiary` |
