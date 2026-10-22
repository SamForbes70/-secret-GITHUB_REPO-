"""Verify byte-level and content-hash determinism across repeated renders."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from shapely.geometry import box

from maps4u.core.config import Settings
from maps4u.core.db import run_migrations
from maps4u.core.ids import sha256_hex
from maps4u.core.models import BBox
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import load_features_from_gpkg
from maps4u.labels.engine import place_labels
from maps4u.layout.furniture import compose_furniture
from maps4u.layout.templates import get_template
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, CairoCanvas
from maps4u.render.style_engine import load_style_yaml, style_plan


def main() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "overpass" / "mcy_sample.json"
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        settings = Settings(
            maps4u_data_dir=base,
            maps4u_db_path=base / "maps4u.db",
            maps4u_overpass_url=f"file://{fixture_path}",
            maps4u_env="test",
        )
        settings.ensure_dirs()
        run_migrations(settings.db_path)

        bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
        extract = get_or_fetch(
            bbox=bbox,
            classes=["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"],
            settings=settings,
        )
        features = load_features_from_gpkg(extract.gpkg_path)
        geofence = box(153.085, -26.660, 153.105, -26.645)
        tpl = get_template("A4", "landscape")
        style = load_style_yaml()
        plan = style_plan(features, geofence, tpl, style, scale_denominator=12500.0)

        hashes: list[tuple[str, str]] = []
        for idx in (1, 2):
            c = CairoCanvas()
            c.set_page(tpl.page_mm, bleed_mm=tpl.bleed_mm)
            fid = c.embedded_font(DEFAULT_TTF_PATH)
            lbls = place_labels(features, geofence, plan, tpl, style, c, fid, seed=0)
            for prim in plan.primitives:
                c.path(prim.ops, prim.stroke, prim.fill)
            compose_furniture(c, plan, lbls, tpl, style, fid, area_name="Maroochydore", edition="2026-10")
            pdf_p = base / f"run_{idx}" / "proof.pdf"
            c.save_pdf(pdf_p)
            hashes.append((c.content_hash(), sha256_hex(pdf_p.read_bytes())))

        assert hashes[0] == hashes[1], f"Determinism mismatch: {hashes[0]} != {hashes[1]}"
        print(json.dumps({"deterministic": True, "content_hash": hashes[0][0], "pdf_sha256": hashes[0][1]}, indent=2))


if __name__ == "__main__":
    main()
