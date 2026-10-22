"""Renderer-agnostic Canvas protocol and canonical draw-log recorder (Appendix C)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from maps4u.core.ids import canonical_json_bytes, sha256_hex


@dataclass(frozen=True)
class Stroke:
    color: str
    width_mm: float
    dash: list[float] | None = None


@dataclass(frozen=True)
class Fill:
    color: str


@dataclass(frozen=True)
class PathOps:
    commands: list[tuple[str, tuple[float, ...]]]


@dataclass(frozen=True)
class GlyphPlacement:
    text: str
    x_mm: float
    y_mm: float
    angle_deg: float
    font_id: str
    size_mm: float
    color: str = "#000000"


class Canvas(Protocol):
    """Binding Canvas protocol per Appendix C."""

    def set_page(self, size_mm: tuple[float, float], bleed_mm: float) -> None: ...
    def path(self, ops: PathOps, stroke: Stroke | None, fill: Fill | None) -> None: ...
    def text(self, glyphs: list[GlyphPlacement]) -> None: ...
    def embedded_font(self, ttf_path: Path) -> str: ...
    def measure_text_mm(self, text: str, font_id: str, size_mm: float) -> tuple[float, float]: ...
    def save_pdf(self, path: Path) -> None: ...


@dataclass
class RecordingCanvas:
    """Deterministic draw-log Canvas implementation for testing and golden op-log generation."""

    page_size_mm: tuple[float, float] = (297.0, 210.0)
    bleed_mm: float = 0.0
    ops_log: list[dict[str, Any]] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)

    def set_page(self, size_mm: tuple[float, float], bleed_mm: float) -> None:
        self.page_size_mm = (round(size_mm[0], 4), round(size_mm[1], 4))
        self.bleed_mm = round(bleed_mm, 4)
        self.ops_log.append(
            {"op": "set_page", "size_mm": list(self.page_size_mm), "bleed_mm": self.bleed_mm}
        )

    def path(self, ops: PathOps, stroke: Stroke | None, fill: Fill | None) -> None:
        self.ops_log.append(
            {
                "op": "path",
                "commands": [[cmd, [round(v, 4) for v in coords]] for cmd, coords in ops.commands],
                "stroke": asdict(stroke) if stroke else None,
                "fill": asdict(fill) if fill else None,
            }
        )

    def text(self, glyphs: list[GlyphPlacement]) -> None:
        self.ops_log.append(
            {"op": "text", "glyphs": [asdict(g) for g in glyphs]}
        )

    def embedded_font(self, ttf_path: Path) -> str:
        digest = sha256_hex(ttf_path.read_bytes())[:12] if ttf_path.exists() else "virtual"
        font_id = f"font-{ttf_path.stem}-{digest}"
        self.fonts[font_id] = str(ttf_path)
        self.ops_log.append({"op": "embedded_font", "font_id": font_id, "name": ttf_path.name})
        return font_id

    def measure_text_mm(self, text: str, font_id: str, size_mm: float) -> tuple[float, float]:
        del font_id
        return (round(max(2.0, len(text) * size_mm * 0.56), 4), round(size_mm * 1.15, 4))

    def drawlog_dict(self) -> dict[str, Any]:
        return {
            "page_size_mm": list(self.page_size_mm),
            "bleed_mm": self.bleed_mm,
            "ops": self.ops_log,
        }

    def content_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self.drawlog_dict()))

    def save_pdf(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        drawlog_path = path.parent / "drawlog.json"
        drawlog_path.write_text(
            json.dumps(self.drawlog_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        path.write_bytes(b"%PDF-1.4 Maps4U RecordingCanvas Stub %%EOF")
