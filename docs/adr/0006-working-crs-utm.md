# ADR-0006: Metric Working CRS via Centroid UTM Zone

- **Status:** Accepted
- **Context:** Web Mercator distorts metric scale calculations.
- **Decision:** Store geofences and cached snapshots in EPSG:4326 on disk, and reproject to the centroid's UTM zone (e.g. EPSG:32756 for SE Queensland) for all metric scale, buffer, and layout math.
