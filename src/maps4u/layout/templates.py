"""Paper template loader and usable map-area frame resolver (§5.4, S2.T1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from maps4u.core.errors import E_STYLE_INVALID, Maps4UError
from maps4u.core.models import Orientation, PaperSize

DEFAULT_TEMPLATES_PATH = Path(__file__).resolve().parents[3] / "config" / "paper_templates.yaml"


@dataclass(frozen=True)
class RectMM:
    """Axis-aligned rectangle in millimetres from top-left page origin."""

    x: float
    y: float
    w: float
    h: float

    @property
    def area_mm2(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def intersects(self, other: RectMM) -> bool:
        eps = 1e-6
        return not (
            self.right <= other.x + eps
            or other.right <= self.x + eps
            or self.bottom <= other.y + eps
            or other.bottom <= self.y + eps
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "w": round(self.w, 3),
            "h": round(self.h, 3),
        }


@dataclass(frozen=True)
class MarginsMM:
    top: float
    right: float
    bottom: float
    left: float


@dataclass(frozen=True)
class GridSpec:
    enabled: bool
    cell_mm: float
    labels: bool


@dataclass(frozen=True)
class PaperTemplate:
    """Resolved paper template including computed map_area_mm."""

    key: str
    paper: PaperSize
    orientation: Orientation
    page_w_mm: float
    page_h_mm: float
    bleed_mm: float
    margins_mm: dict[str, float]
    furniture: dict[str, RectMM]
    map_area_mm: RectMM
    grid: GridSpec

    @property
    def page_mm(self) -> tuple[float, float]:
        return (self.page_w_mm, self.page_h_mm)

    @property
    def page_area_mm2(self) -> float:
        return self.page_w_mm * self.page_h_mm

    @property
    def inner_frame_mm(self) -> RectMM:
        return RectMM(
            x=self.margins_mm["left"],
            y=self.margins_mm["top"],
            w=self.page_w_mm - self.margins_mm["left"] - self.margins_mm["right"],
            h=self.page_h_mm - self.margins_mm["top"] - self.margins_mm["bottom"],
        )


def resolve_map_area_mm(
    page_w_mm: float,
    page_h_mm: float,
    margins_mm: dict[str, float],
    furniture: dict[str, RectMM],
) -> RectMM:
    """Compute the largest axis-aligned rectangle inside margins excluding reserved furniture cells."""
    ix0 = float(margins_mm["left"])
    iy0 = float(margins_mm["top"])
    ix1 = float(page_w_mm) - float(margins_mm["right"])
    iy1 = float(page_h_mm) - float(margins_mm["bottom"])
    if ix1 <= ix0 or iy1 <= iy0:
        raise Maps4UError(E_STYLE_INVALID, "Invalid page margins: inner frame is non-positive")

    xs = sorted(
        {
            ix0,
            ix1,
            *[max(ix0, min(ix1, r.x)) for r in furniture.values()],
            *[max(ix0, min(ix1, r.right)) for r in furniture.values()],
        }
    )
    ys = sorted(
        {
            iy0,
            iy1,
            *[max(iy0, min(iy1, r.y)) for r in furniture.values()],
            *[max(iy0, min(iy1, r.bottom)) for r in furniture.values()],
        }
    )

    best = RectMM(x=ix0, y=iy0, w=0.0, h=0.0)
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1 :]:
            w = x1 - x0
            if w <= 0:
                continue
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1 :]:
                    h = y1 - y0
                    if w * h <= best.area_mm2:
                        continue
                    candidate = RectMM(x=x0, y=y0, w=w, h=h)
                    if any(candidate.intersects(f) for f in furniture.values()):
                        continue
                    best = candidate

    if best.area_mm2 <= 0:
        raise Maps4UError(E_STYLE_INVALID, "Could not resolve a positive map_area_mm")
    return best


def load_paper_templates(path: Path | None = None) -> dict[str, PaperTemplate]:
    """Load and resolve all 6 paper templates from config/paper_templates.yaml."""
    cfg_path = path or DEFAULT_TEMPLATES_PATH
    if not cfg_path.is_file():
        raise Maps4UError(E_STYLE_INVALID, f"Paper templates file not found: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise Maps4UError(E_STYLE_INVALID, "paper_templates.yaml root must be a mapping")

    resolved: dict[str, PaperTemplate] = {}
    for key in sorted(raw.keys()):
        entry = raw[key]
        parts = str(key).split("-", 1)
        if len(parts) != 2 or parts[0] not in ("A3", "A4", "A5") or parts[1] not in ("landscape", "portrait"):
            raise Maps4UError(E_STYLE_INVALID, f"Invalid paper template key: {key!r}")

        paper = cast(PaperSize, parts[0])
        orientation = cast(Orientation, parts[1])
        page_mm = entry["page_mm"]
        page_w_mm = float(page_mm[0])
        page_h_mm = float(page_mm[1])
        bleed_mm = float(entry.get("bleed_mm", 3.0))
        margins_raw = entry["margins_mm"]
        margins_mm = {
            "top": float(margins_raw["top"]),
            "right": float(margins_raw["right"]),
            "bottom": float(margins_raw["bottom"]),
            "left": float(margins_raw["left"]),
        }
        furn_raw = entry.get("furniture", {})
        furniture: dict[str, RectMM] = {}
        for fk in sorted(furn_raw.keys()):
            fv = furn_raw[fk]
            furniture[fk] = RectMM(
                x=float(fv["x"]),
                y=float(fv["y"]),
                w=float(fv["w"]),
                h=float(fv["h"]),
            )

        explicit_map = entry.get("map_area_mm")
        if isinstance(explicit_map, dict):
            map_area = RectMM(
                x=float(explicit_map["x"]),
                y=float(explicit_map["y"]),
                w=float(explicit_map["w"]),
                h=float(explicit_map["h"]),
            )
        else:
            map_area = resolve_map_area_mm(page_w_mm, page_h_mm, margins_mm, furniture)

        grid_raw = entry.get("grid", {})
        grid = GridSpec(
            enabled=bool(grid_raw.get("enabled", True)),
            cell_mm=float(grid_raw.get("cell_mm", 40.0)),
            labels=bool(grid_raw.get("labels", True)),
        )

        resolved[key] = PaperTemplate(
            key=key,
            paper=paper,
            orientation=orientation,
            page_w_mm=page_w_mm,
            page_h_mm=page_h_mm,
            bleed_mm=bleed_mm,
            margins_mm=margins_mm,
            furniture=furniture,
            map_area_mm=map_area,
            grid=grid,
        )
    return resolved


load_all_templates = load_paper_templates


def get_template(
    paper: PaperSize,
    orientation: Orientation,
    path: Path | None = None,
) -> PaperTemplate:
    """Return a single resolved PaperTemplate for (paper, orientation)."""
    templates = load_paper_templates(path=path)
    key = f"{paper}-{orientation}"
    if key not in templates:
        raise Maps4UError(E_STYLE_INVALID, f"Paper template not found: {key}")
    return templates[key]


def template_to_dict(tpl: PaperTemplate) -> dict[str, Any]:
    """Serialise PaperTemplate to plain dictionary."""
    return {
        "key": tpl.key,
        "paper": tpl.paper,
        "orientation": tpl.orientation,
        "page_mm": [tpl.page_w_mm, tpl.page_h_mm],
        "bleed_mm": tpl.bleed_mm,
        "margins_mm": tpl.margins_mm,
        "furniture": {k: v.to_dict() for k, v in tpl.furniture.items()},
        "map_area_mm": tpl.map_area_mm.to_dict(),
        "grid": {
            "enabled": tpl.grid.enabled,
            "cell_mm": tpl.grid.cell_mm,
            "labels": tpl.grid.labels,
        },
    }
