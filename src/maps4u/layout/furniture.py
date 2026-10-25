"""Map furniture composer: title block, north arrow, scale bar, legend, grid, street index, attribution, watermark."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from maps4u.labels.engine import LabelResult
from maps4u.layout.templates import PaperTemplate, RectMM
from maps4u.render.canvas import Canvas, Fill, GlyphPlacement, PathOps, Stroke
from maps4u.render.style_engine import DrawPlan, LoadedStyle


@dataclass(frozen=True)
class GridIndexEntry:
    name: str
    feature_class: str
    cell: str


@dataclass(frozen=True)
class ComposedLayout:
    template_key: str
    area_name: str
    edition: str
    scale_denominator: float
    legend_classes: list[str] = field(default_factory=list)
    grid_cells: list[str] = field(default_factory=list)
    street_index: list[GridIndexEntry] = field(default_factory=list)
    has_attribution: bool = True
    has_watermark: bool = True
    inset_enabled: bool = False
    page_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


def _col_letters(idx: int) -> str:
    return chr(ord("A") + (idx % 26))


def compose_furniture(
    canvas: Canvas,
    plan: DrawPlan,
    labels: LabelResult,
    template: PaperTemplate,
    style: LoadedStyle,
    font_id: str,
    area_name: str = "Maroochydore",
    edition: str = "2026-10",
    watermark_text: str | None = "PROOF — NOT FOR DISTRIBUTION",
    insets_enabled: bool = False,
) -> ComposedLayout:
    layers_cfg = style.raw.get("layers", {})
    map_rect = template.map_area_mm
    glyphs: list[GlyphPlacement] = []

    # Emit placed map labels first
    for pl in labels.placed:
        glyphs.append(pl.to_glyph())

    # 1. Alphanumeric Grid Overlay & Cell Index (A1..Hn)
    grid_cells: list[str] = []
    cell_mm = max(20.0, float(template.grid.cell_mm))
    n_cols = max(2, int(math.ceil(map_rect.w / cell_mm)))
    n_rows = max(2, int(math.ceil(map_rect.h / cell_mm)))
    col_w = map_rect.w / n_cols
    row_h = map_rect.h / n_rows

    if template.grid.enabled:
        grid_stroke = Stroke("#94a3b8", 0.12, [1.2, 1.2])
        for c_idx in range(1, n_cols):
            gx = round(map_rect.x + c_idx * col_w, 3)
            canvas.path(
                PathOps([("M", (gx, map_rect.y)), ("L", (gx, map_rect.bottom))]),
                grid_stroke,
                None,
            )
        for r_idx in range(1, n_rows):
            gy = round(map_rect.y + r_idx * row_h, 3)
            canvas.path(
                PathOps([("M", (map_rect.x, gy)), ("L", (map_rect.right, gy))]),
                grid_stroke,
                None,
            )

    for c_idx in range(n_cols):
        col_lbl = _col_letters(c_idx)
        if template.grid.labels:
            glyphs.append(
                GlyphPlacement(
                    text=col_lbl,
                    x_mm=round(map_rect.x + (c_idx + 0.45) * col_w, 3),
                    y_mm=round(map_rect.y + 2.2, 3),
                    angle_deg=0.0,
                    font_id=font_id,
                    size_mm=1.6,
                    color="#475569",
                )
            )
        for r_idx in range(n_rows):
            cell_id = f"{col_lbl}{r_idx + 1}"
            grid_cells.append(cell_id)
            if c_idx == 0 and template.grid.labels:
                glyphs.append(
                    GlyphPlacement(
                        text=str(r_idx + 1),
                        x_mm=round(map_rect.x + 1.0, 3),
                        y_mm=round(map_rect.y + (r_idx + 0.55) * row_h, 3),
                        angle_deg=0.0,
                        font_id=font_id,
                        size_mm=1.6,
                        color="#475569",
                    )
                )

    # Build Street & Feature Grid Index from placed labels
    seen_names: set[tuple[str, str]] = set()
    street_index: list[GridIndexEntry] = []
    for pl in sorted(labels.placed, key=lambda item: (item.text, item.feature_class)):
        key = (pl.text, pl.feature_class)
        if key in seen_names:
            continue
        seen_names.add(key)
        c_idx = min(n_cols - 1, max(0, int((pl.x_mm - map_rect.x) / col_w)))
        r_idx = min(n_rows - 1, max(0, int((pl.y_mm - map_rect.y) / row_h)))
        cell_ref = f"{_col_letters(c_idx)}{r_idx + 1}"
        street_index.append(GridIndexEntry(name=pl.text, feature_class=pl.feature_class, cell=cell_ref))

    # 2. Title Block
    title_rect = template.furniture.get("title_block_mm")
    if title_rect is not None:
        canvas.path(
            PathOps(
                [
                    ("M", (title_rect.x, title_rect.y)),
                    ("L", (title_rect.right, title_rect.y)),
                    ("L", (title_rect.right, title_rect.bottom)),
                    ("L", (title_rect.x, title_rect.bottom)),
                    ("Z", ()),
                ]
            ),
            Stroke("#334155", 0.35),
            Fill("#ffffff"),
        )
        glyphs.append(
            GlyphPlacement(
                text=f"{area_name} Street Map — Edition {edition} (1:{int(round(plan.scale_denominator))})",
                x_mm=round(title_rect.x + 2.5, 3),
                y_mm=round(title_rect.y + title_rect.h * 0.65, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=3.2,
                color="#0f172a",
            )
        )

    # 3. Auto-Generated Legend from layers actually present in DrawPlan
    present_layers = sorted({p.layer for p in plan.primitives if p.layer != "background"})
    legend_rect = template.furniture.get("legend_mm")
    if legend_rect is not None:
        canvas.path(
            PathOps(
                [
                    ("M", (legend_rect.x, legend_rect.y)),
                    ("L", (legend_rect.right, legend_rect.y)),
                    ("L", (legend_rect.right, legend_rect.bottom)),
                    ("L", (legend_rect.x, legend_rect.bottom)),
                    ("Z", ()),
                ]
            ),
            Stroke("#475569", 0.3),
            Fill("#ffffff"),
        )
        glyphs.append(
            GlyphPlacement(
                text="LEGEND",
                x_mm=round(legend_rect.x + 2.0, 3),
                y_mm=round(legend_rect.y + 4.5, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=2.2,
                color="#0f172a",
            )
        )
        for idx, lyr in enumerate(present_layers[:6]):
            ly = round(legend_rect.y + 8.5 + idx * 4.2, 3)
            if ly + 2.0 <= legend_rect.bottom:
                sx = round(legend_rect.x + 2.5, 3)
                sy = round(ly - 1.5, 3)
                sw = 5.5
                sh = 1.9
                if lyr == "water":
                    w_cfg = layers_cfg.get("water", {})
                    canvas.path(
                        PathOps(
                            [("M", (sx, sy)), ("L", (sx + sw, sy)), ("L", (sx + sw, sy + sh)), ("L", (sx, sy + sh)), ("Z", ())]
                        ),
                        Stroke(str((w_cfg.get("stroke") or {}).get("color", "#76b4c6")), 0.2),
                        Fill(str(w_cfg.get("fill", "#aad3df"))),
                    )
                elif lyr == "parks":
                    p_cfg = layers_cfg.get("parks", {})
                    canvas.path(
                        PathOps(
                            [("M", (sx, sy)), ("L", (sx + sw, sy)), ("L", (sx + sw, sy + sh)), ("L", (sx, sy + sh)), ("Z", ())]
                        ),
                        Stroke(str((p_cfg.get("stroke") or {}).get("color", "#9ccc9c")), 0.2),
                        Fill(str(p_cfg.get("fill", "#c8e6c9"))),
                    )
                elif lyr == "roads":
                    mid_y = round(sy + sh * 0.5, 3)
                    canvas.path(
                        PathOps([("M", (sx, mid_y)), ("L", (sx + sw, mid_y))]),
                        Stroke("#4a4a4a", 1.15),
                        None,
                    )
                    canvas.path(
                        PathOps([("M", (sx, mid_y)), ("L", (sx + sw, mid_y))]),
                        Stroke("#ffe082", 0.78),
                        None,
                    )
                elif lyr == "water_lines":
                    wl_cfg = layers_cfg.get("water_lines", {})
                    mid_y = round(sy + sh * 0.5, 3)
                    canvas.path(
                        PathOps([("M", (sx, mid_y)), ("L", (sx + sw, mid_y))]),
                        Stroke(str((wl_cfg.get("stroke") or {}).get("color", "#76b4c6")), 0.45),
                        None,
                    )
                elif lyr == "coastline":
                    cl_cfg = layers_cfg.get("coastline", {})
                    mid_y = round(sy + sh * 0.5, 3)
                    canvas.path(
                        PathOps([("M", (sx, mid_y)), ("L", (sx + sw, mid_y))]),
                        Stroke(str((cl_cfg.get("stroke") or {}).get("color", "#4a8fa3")), 0.40),
                        None,
                    )
                else:
                    b_cfg = layers_cfg.get("boundaries", {})
                    mid_y = round(sy + sh * 0.5, 3)
                    canvas.path(
                        PathOps([("M", (sx, mid_y)), ("L", (sx + sw, mid_y))]),
                        Stroke(str((b_cfg.get("stroke") or {}).get("color", "#7c6f64")), 0.35, [1.2, 1.0]),
                        None,
                    )
                glyphs.append(
                    GlyphPlacement(
                        text=lyr.replace("_", " ").title(),
                        x_mm=round(legend_rect.x + 9.5, 3),
                        y_mm=ly,
                        angle_deg=0.0,
                        font_id=font_id,
                        size_mm=1.7,
                        color="#1e293b",
                    )
                )

    # 3b. Street Index Panel (right sidebar on landscape; below title block on portrait)
    na_rect_for_idx = template.furniture.get("north_arrow_mm")
    index_rect: RectMM | None = None
    if template.orientation == "landscape" and legend_rect is not None:
        idx_bottom = (na_rect_for_idx.y - 3.0) if na_rect_for_idx is not None else (map_rect.bottom - 2.0)
        idx_h = round(idx_bottom - (legend_rect.bottom + 2.5), 3)
        if idx_h >= 18.0:
            index_rect = RectMM(x=legend_rect.x, y=round(legend_rect.bottom + 2.5, 3), w=legend_rect.w, h=idx_h)
    elif template.orientation == "portrait" and title_rect is not None:
        idx_h = round(map_rect.y - (title_rect.bottom + 2.0) - 2.0, 3)
        if idx_h >= 14.0:
            index_rect = RectMM(x=title_rect.x, y=round(title_rect.bottom + 2.0, 3), w=title_rect.w, h=idx_h)

    if index_rect is not None and street_index:
        canvas.path(
            PathOps(
                [
                    ("M", (index_rect.x, index_rect.y)),
                    ("L", (index_rect.right, index_rect.y)),
                    ("L", (index_rect.right, index_rect.bottom)),
                    ("L", (index_rect.x, index_rect.bottom)),
                    ("Z", ()),
                ]
            ),
            Stroke("#475569", 0.3),
            Fill("#ffffff"),
        )
        glyphs.append(
            GlyphPlacement(
                text="STREET INDEX",
                x_mm=round(index_rect.x + 2.0, 3),
                y_mm=round(index_rect.y + 3.8, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=1.8,
                color="#0f172a",
            )
        )
        n_idx_cols = 2 if template.orientation == "landscape" else 3
        col_idx_w = (index_rect.w - 3.0) / n_idx_cols
        row_step = 2.5
        start_y = index_rect.y + 6.8
        max_rows_per_col = max(1, int((index_rect.bottom - 1.5 - start_y) // row_step))
        max_chars = 15 if n_idx_cols == 2 else 18
        road_entries = [e for e in street_index if e.feature_class in ("arterial", "collector", "local", "service")]
        display_entries = road_entries if road_entries else street_index
        for e_idx, entry in enumerate(display_entries[: max_rows_per_col * n_idx_cols]):
            c_i = e_idx // max_rows_per_col
            r_i = e_idx % max_rows_per_col
            ex = round(index_rect.x + 1.8 + c_i * col_idx_w, 3)
            ey = round(start_y + r_i * row_step, 3)
            short_name = entry.name if len(entry.name) <= max_chars else (entry.name[: max_chars - 1].rstrip() + "…")
            glyphs.append(
                GlyphPlacement(
                    text=f"{short_name} [{entry.cell}]",
                    x_mm=ex,
                    y_mm=ey,
                    angle_deg=0.0,
                    font_id=font_id,
                    size_mm=1.35,
                    color="#1e293b",
                )
            )

    # 4. Metric Scale Bar
    sb_rect = template.furniture.get("scalebar_mm") or template.furniture.get("scale_bar_mm")
    if sb_rect is not None:
        bar_w = min(sb_rect.w * 0.65, 40.0)
        bx = round(sb_rect.x + 2.0, 3)
        by = round(sb_rect.y + sb_rect.h * 0.45, 3)
        canvas.path(
            PathOps([("M", (bx, by)), ("L", (bx + bar_w, by))]),
            Stroke("#0f172a", 0.6),
            None,
        )
        ground_m = int(round((bar_w / 1000.0) * plan.scale_denominator))
        glyphs.append(
            GlyphPlacement(
                text=f"0 — {ground_m} m",
                x_mm=bx,
                y_mm=round(sb_rect.bottom - 1.5, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=1.7,
                color="#0f172a",
            )
        )

    # 5. North Arrow
    na_rect = template.furniture.get("north_arrow_mm")
    if na_rect is not None:
        cx = round(na_rect.x + na_rect.w / 2.0, 3)
        top_y = round(na_rect.y + 2.0, 3)
        bot_y = round(na_rect.bottom - 4.0, 3)
        canvas.path(
            PathOps(
                [
                    ("M", (cx, top_y)),
                    ("L", (cx - 2.5, bot_y)),
                    ("L", (cx + 2.5, bot_y)),
                    ("Z", ()),
                ]
            ),
            Stroke("#0f172a", 0.3),
            Fill("#0f172a"),
        )
        glyphs.append(
            GlyphPlacement(
                text="N",
                x_mm=round(cx - 1.2, 3),
                y_mm=round(na_rect.bottom - 1.0, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=2.2,
                color="#0f172a",
            )
        )

    # 6. Mandatory ODbL Attribution
    attr_rect = template.furniture.get("attribution_mm")
    attr_x = round(attr_rect.x + 1.0, 3) if attr_rect is not None else round(map_rect.x, 3)
    attr_y = round(attr_rect.y + attr_rect.h * 0.70, 3) if attr_rect is not None else round(template.page_h_mm - 3.0, 3)
    glyphs.append(
        GlyphPlacement(
            text=f"Map data (c) OpenStreetMap contributors (ODbL) | Style {plan.style_ref}",
            x_mm=attr_x,
            y_mm=attr_y,
            angle_deg=0.0,
            font_id=font_id,
            size_mm=1.6,
            color="#334155",
        )
    )

    # 7. Proof Watermark
    has_wm = bool(watermark_text)
    if watermark_text:
        wm_rect = template.furniture.get("watermark_mm")
        wx = round(wm_rect.x + 2.0, 3) if wm_rect is not None else round(map_rect.x + map_rect.w * 0.28, 3)
        wy = round(wm_rect.y + wm_rect.h * 0.65, 3) if wm_rect is not None else round(map_rect.y + map_rect.h * 0.52, 3)
        glyphs.append(
            GlyphPlacement(
                text=watermark_text,
                x_mm=wx,
                y_mm=wy,
                angle_deg=18.0,
                font_id=font_id,
                size_mm=3.8,
                color="#94a3b8",
            )
        )

    canvas.text(glyphs)

    page_count = 2 if insets_enabled else 1
    return ComposedLayout(
        template_key=template.key,
        area_name=area_name,
        edition=edition,
        scale_denominator=plan.scale_denominator,
        legend_classes=present_layers,
        grid_cells=grid_cells,
        street_index=street_index,
        has_attribution=True,
        has_watermark=has_wm,
        inset_enabled=insets_enabled,
        page_count=page_count,
        metadata={
            "grid_cols": n_cols,
            "grid_rows": n_rows,
            "placed_labels": len(labels.placed),
            "street_index_count": len(street_index),
            "reverse_side_index_enabled": insets_enabled,
        },
    )
