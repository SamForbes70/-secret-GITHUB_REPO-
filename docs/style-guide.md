# Maps4U Cartographic Style Authoring Guide (`styles/mcy/v1/style.yaml`)

All cartographic styling rules live in YAML (`styles/mcy/v1/style.yaml`) and are validated at load time against `schemas/style.schema.json`. Zero colours, line widths, or font sizes are hardcoded in Python.

## Structure of `style.yaml`
- **`meta`:** `id`, `name`, `version`, `min_font_mm` (`1.5 mm` hard floor), and `max_scale_denominator` (`25000`).
- **`scale_bands`:** `detail` (`<= 1:10,000`), `standard_street` (`1:10,000 - 1:17,500`), and `overview` (`> 1:17,500`).
- **`palette`:** Background, water fill/stroke, park fill/stroke, boundary stroke, and grid stroke hex colours.
- **`z_order`:** Monotonic rendering stack (`background` -> `water` -> `parks` -> `water_lines` -> `coastline` -> `roads_casing` -> `roads_fill` -> `boundaries` -> `labels` -> `furniture`).
- **`roads`:** Per-class (`motorway`, `primary`, `secondary`, `tertiary`, `residential`, `service`) casing width, fill width, colours, minimum scale band, and label font size (`mm`).
