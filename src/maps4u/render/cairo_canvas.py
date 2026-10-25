"""Deterministic Vector PDF + Thumbnail Canvas implementation (Stage 3 S3.T1, ADR-1)."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas

from maps4u.core.ids import canonical_json_bytes, sha256_hex
from maps4u.render.canvas import Fill, GlyphPlacement, PathOps, Stroke

PT_PER_MM = 72.0 / 25.4
DEFAULT_TTF_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _hex_to_rgb_floats(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (round(r, 4), round(g, 4), round(b, 4))


def _hex_to_rgb_ints(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


@dataclass
class CairoCanvas:
    """Deterministic vector PDF and raster thumbnail Canvas implementation (ADR-1)."""

    page_size_mm: tuple[float, float] = (297.0, 210.0)
    bleed_mm: float = 3.0
    ops_log: list[dict[str, Any]] = field(default_factory=list)
    fonts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _path_records: list[tuple[PathOps, Stroke | None, Fill | None]] = field(default_factory=list)
    _glyph_records: list[GlyphPlacement] = field(default_factory=list)

    def set_page(self, size_mm: tuple[float, float], bleed_mm: float) -> None:
        self.page_size_mm = (round(float(size_mm[0]), 4), round(float(size_mm[1]), 4))
        self.bleed_mm = round(float(bleed_mm), 4)
        self.ops_log.append(
            {"op": "set_page", "size_mm": list(self.page_size_mm), "bleed_mm": self.bleed_mm}
        )

    def path(self, ops: PathOps, stroke: Stroke | None, fill: Fill | None) -> None:
        self._path_records.append((ops, stroke, fill))
        self.ops_log.append(
            {
                "op": "path",
                "commands": [[cmd, [round(v, 4) for v in coords]] for cmd, coords in ops.commands],
                "stroke": asdict(stroke) if stroke else None,
                "fill": asdict(fill) if fill else None,
            }
        )

    def text(self, glyphs: list[GlyphPlacement]) -> None:
        self._glyph_records.extend(glyphs)
        self.ops_log.append(
            {
                "op": "text",
                "glyphs": [
                    {
                        "text": g.text,
                        "x_mm": round(g.x_mm, 4),
                        "y_mm": round(g.y_mm, 4),
                        "angle_deg": round(g.angle_deg, 4),
                        "font_id": g.font_id,
                        "size_mm": round(g.size_mm, 4),
                        "color": g.color,
                    }
                    for g in glyphs
                ],
            }
        )

    def embedded_font(self, ttf_path: Path) -> str:
        resolved = ttf_path if ttf_path.exists() else DEFAULT_TTF_PATH
        raw = resolved.read_bytes() if resolved.exists() else b"DejaVuSans"
        digest = sha256_hex(raw)[:12]
        font_id = f"F{len(self.fonts) + 1}"
        if font_id not in self.fonts:
            self.fonts[font_id] = {
                "font_id": font_id,
                "name": resolved.stem,
                "path": str(resolved),
                "sha256": sha256_hex(raw),
                "digest12": digest,
            }
        self.ops_log.append(
            {
                "op": "embedded_font",
                "font_id": font_id,
                "name": resolved.stem,
                "sha256": sha256_hex(raw),
            }
        )
        return font_id

    def measure_text_mm(self, text: str, font_id: str, size_mm: float) -> tuple[float, float]:
        if not text:
            return (0.0, round(size_mm, 4))
        font_info = self.fonts.get(font_id, {})
        ttf_str = font_info.get("path", str(DEFAULT_TTF_PATH))
        ttf_file = Path(ttf_str) if Path(ttf_str).exists() else DEFAULT_TTF_PATH
        # Measure at 100 px per mm for high precision
        px_scale = 100.0
        px_size = max(8, int(round(size_mm * px_scale)))
        try:
            fnt = ImageFont.truetype(str(ttf_file), size=px_size)
            bbox = fnt.getbbox(text)
            w_mm = (bbox[2] - bbox[0]) / px_scale
            h_mm = (bbox[3] - bbox[1]) / px_scale
            return (round(max(w_mm, 0.1), 4), round(max(h_mm, size_mm * 0.75), 4))
        except Exception:
            return (round(len(text) * size_mm * 0.58, 4), round(size_mm, 4))

    def drawlog_dict(self) -> dict[str, Any]:
        return {
            "page_size_mm": list(self.page_size_mm),
            "bleed_mm": self.bleed_mm,
            "ops": self.ops_log,
        }

    def content_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self.drawlog_dict()))

    def _build_pdf_content_stream(self) -> bytes:
        w_mm, h_mm = self.page_size_mm
        lines: list[str] = ["q"]

        def _pt_x(x_mm: float) -> float:
            return round(x_mm * PT_PER_MM, 3)

        def _pt_y(y_mm: float) -> float:
            return round((h_mm - y_mm) * PT_PER_MM, 3)

        for ops, stroke, fill in self._path_records:
            if not ops.commands:
                continue
            lines.append("q")
            if fill is not None:
                fr, fg, fb = _hex_to_rgb_floats(fill.color)
                lines.append(f"{fr:.4f} {fg:.4f} {fb:.4f} rg")
            if stroke is not None:
                sr, sg, sb = _hex_to_rgb_floats(stroke.color)
                w_pt = max(0.05, round(stroke.width_mm * PT_PER_MM, 3))
                lines.append(f"{sr:.4f} {sg:.4f} {sb:.4f} RG {w_pt:.3f} w 1 J 1 j")
                if stroke.dash:
                    dash_pts = " ".join(f"{round(d * PT_PER_MM, 3):.3f}" for d in stroke.dash)
                    lines.append(f"[{dash_pts}] 0 d")
                else:
                    lines.append("[] 0 d")

            for cmd, coords in ops.commands:
                if cmd == "M" and len(coords) >= 2:
                    lines.append(f"{_pt_x(coords[0]):.3f} {_pt_y(coords[1]):.3f} m")
                elif cmd == "L" and len(coords) >= 2:
                    lines.append(f"{_pt_x(coords[0]):.3f} {_pt_y(coords[1]):.3f} l")
                elif cmd == "Z":
                    lines.append("h")

            if fill is not None and stroke is not None:
                lines.append("B")
            elif fill is not None:
                lines.append("f")
            elif stroke is not None:
                lines.append("S")
            else:
                lines.append("n")
            lines.append("Q")

        default_fid = next(iter(self.fonts.keys()), "F1")
        for g in self._glyph_records:
            fid = g.font_id if g.font_id in self.fonts else default_fid
            size_pt = max(1.0, round(g.size_mm * PT_PER_MM, 3))
            cr, cg, cb = _hex_to_rgb_floats(g.color)
            tx = _pt_x(g.x_mm)
            ty = _pt_y(g.y_mm)
            rad = math.radians(-g.angle_deg)
            cos_a = round(math.cos(rad), 4)
            sin_a = round(math.sin(rad), 4)
            esc = _escape_pdf_text(g.text)
            lines.append(
                f"BT /{fid} {size_pt:.3f} Tf {cr:.4f} {cg:.4f} {cb:.4f} rg "
                f"{cos_a:.4f} {sin_a:.4f} {-sin_a:.4f} {cos_a:.4f} {tx:.3f} {ty:.3f} Tm "
                f"({esc}) Tj ET"
            )

        lines.append("Q")
        return ("\n".join(lines) + "\n").encode("latin-1")

    def save_pdf(self, path: Path) -> None:
        """Write deterministic vector output with real embedded TrueType font programs.

        ReportLab's invariant mode fixes document IDs and timestamps. TTFont
        automatically subsets glyphs used by Unicode strings into a FontFile2
        stream rather than merely declaring a /FontDescriptor.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.fonts:
            self.embedded_font(DEFAULT_TTF_PATH)

        drawlog_path = path.parent / "drawlog.json"
        drawlog_path.write_text(
            json.dumps(self.drawlog_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )

        width_pt = self.page_size_mm[0] * PT_PER_MM
        height_pt = self.page_size_mm[1] * PT_PER_MM
        pdf = pdf_canvas.Canvas(
            str(path),
            pagesize=(width_pt, height_pt),
            pageCompression=0,
            invariant=1,
        )
        pdf.setTitle("Maps4U Street Map Proof")
        pdf.setAuthor("Maps4U")
        pdf.setSubject("Map data OpenStreetMap contributors ODbL")
        pdf.setCreator("Maps4U Deterministic Vector Renderer")

        font_names: dict[str, str] = {}
        for font_id, info in sorted(self.fonts.items()):
            ttf_path = Path(str(info["path"]))
            if not ttf_path.is_file():
                raise FileNotFoundError(f"Required TrueType font missing: {ttf_path}")
            stable_name = f"Maps4U-{info['digest12']}"
            if stable_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(stable_name, str(ttf_path)))
            font_names[font_id] = stable_name

        for operations, stroke, fill in self._path_records:
            if not operations.commands:
                continue
            pdf.saveState()
            path_obj = pdf.beginPath()
            for command, coords in operations.commands:
                if command == "M" and len(coords) >= 2:
                    path_obj.moveTo(coords[0] * PT_PER_MM, height_pt - coords[1] * PT_PER_MM)
                elif command == "L" and len(coords) >= 2:
                    path_obj.lineTo(coords[0] * PT_PER_MM, height_pt - coords[1] * PT_PER_MM)
                elif command == "Z":
                    path_obj.close()
            if fill is not None:
                pdf.setFillColor(HexColor(fill.color))
            if stroke is not None:
                pdf.setStrokeColor(HexColor(stroke.color))
                pdf.setLineWidth(max(0.05, stroke.width_mm * PT_PER_MM))
                pdf.setLineCap(1)
                pdf.setLineJoin(1)
                if stroke.dash:
                    pdf.setDash([v * PT_PER_MM for v in stroke.dash])
            pdf.drawPath(path_obj, stroke=int(stroke is not None), fill=int(fill is not None))
            pdf.restoreState()

        default_name = next(iter(font_names.values()))
        for glyph in self._glyph_records:
            pdf.saveState()
            pdf.translate(glyph.x_mm * PT_PER_MM, height_pt - glyph.y_mm * PT_PER_MM)
            pdf.rotate(-glyph.angle_deg)
            pdf.setFillColor(HexColor(glyph.color))
            pdf.setFont(font_names.get(glyph.font_id, default_name), max(1.0, glyph.size_mm * PT_PER_MM))
            pdf.drawString(0, 0, glyph.text)
            pdf.restoreState()

        pdf.showPage()
        pdf.save()

    def render_pdf(self, path: Path) -> None:
        self.save_pdf(path)

    def render_thumbnail(self, path: Path, dpi: int = 120) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        px_per_mm = dpi / 25.4
        w_px = max(64, int(round(self.page_size_mm[0] * px_per_mm)))
        h_px = max(64, int(round(self.page_size_mm[1] * px_per_mm)))
        img = Image.new("RGB", (w_px, h_px), (249, 246, 239))
        draw = ImageDraw.Draw(img)

        for ops, stroke, fill in self._path_records:
            pts: list[tuple[float, float]] = []
            closed = False
            for cmd, coords in ops.commands:
                if cmd in ("M", "L") and len(coords) >= 2:
                    pts.append((coords[0] * px_per_mm, coords[1] * px_per_mm))
                elif cmd == "Z":
                    closed = True
            if len(pts) >= 3 and (closed or fill is not None):
                fill_rgb = _hex_to_rgb_ints(fill.color) if fill is not None else None
                outline_rgb = _hex_to_rgb_ints(stroke.color) if stroke is not None else None
                draw.polygon(pts, fill=fill_rgb, outline=outline_rgb)
            elif len(pts) >= 2 and stroke is not None:
                stroke_rgb = _hex_to_rgb_ints(stroke.color)
                width_px = max(1, int(round(stroke.width_mm * px_per_mm)))
                draw.line(pts, fill=stroke_rgb, width=width_px)

        for g in self._glyph_records:
            font_px = max(8, int(round(g.size_mm * px_per_mm)))
            source = Path(str(self.fonts.get(g.font_id, {}).get("path", DEFAULT_TTF_PATH)))
            try:
                fnt = ImageFont.truetype(str(source), size=font_px)
            except Exception:
                fnt = ImageFont.load_default()  # type: ignore[assignment]
            anchor_x = g.x_mm * px_per_mm
            anchor_y = g.y_mm * px_per_mm
            rgb = _hex_to_rgb_ints(g.color)
            if abs(g.angle_deg) < 0.0001:
                draw.text((anchor_x, anchor_y), g.text, fill=rgb, font=fnt, anchor="ls")
                continue

            # Rotate an isolated glyph image around its baseline anchor,
            # matching the vector PDF placement instead of losing the angle.
            left, top, right, bottom = draw.textbbox((0, 0), g.text, font=fnt, anchor="ls")
            padding = max(8, font_px)
            width = max(1, right - left + 2 * padding)
            height = max(1, bottom - top + 2 * padding)
            text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(text_layer).text(
                (padding - left, padding - top),
                g.text,
                fill=(*rgb, 255),
                font=fnt,
                anchor="ls",
            )
            angle = -g.angle_deg
            rotated = text_layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            dx = padding - left - width / 2
            dy = padding - top - height / 2
            radians = math.radians(angle)
            rotated_anchor_x = rotated.width / 2 + dx * math.cos(radians) + dy * math.sin(radians)
            rotated_anchor_y = rotated.height / 2 - dx * math.sin(radians) + dy * math.cos(radians)
            img.paste(
                rotated,
                (
                    int(round(anchor_x - rotated_anchor_x)),
                    int(round(anchor_y - rotated_anchor_y)),
                ),
                rotated,
            )

        img.save(path, format="PNG")


def render_png_thumbnail(canvas: CairoCanvas, path: Path, dpi: int = 120) -> None:
    canvas.render_thumbnail(path, dpi=dpi)
