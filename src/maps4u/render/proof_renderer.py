"""End-to-end Stage 3 Proof PDF + Thumbnail renderer and structural verifier (S3.T3)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader
from PyPDF2.generic import ContentStream
from shapely.geometry import MultiPolygon, Polygon

from maps4u.core.config import Settings
from maps4u.core.ids import sha256_hex
from maps4u.geo.features import FeatureSet
from maps4u.layout.templates import PaperTemplate
from maps4u.render.cairo_canvas import DEFAULT_TTF_PATH, PT_PER_MM, CairoCanvas
from maps4u.render.canvas import GlyphPlacement
from maps4u.render.style_engine import DrawPlan, LoadedStyle, style_plan


@dataclass(frozen=True)
class ProofRenderOutput:
    pdf_path: Path
    thumb_path: Path
    drawlog_path: Path
    pdf_sha256: str
    thumb_sha256: str
    content_hash: str
    plan: DrawPlan
    structural_checks: dict[str, Any] = field(default_factory=dict)


def render_proof(
    features: FeatureSet,
    geofence_wgs84: Polygon | MultiPolygon,
    template: PaperTemplate,
    style: LoadedStyle,
    scale_denominator: float,
    out_dir: Path,
    settings: Settings | None = None,
    area_name: str = "Maroochydore",
) -> ProofRenderOutput:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = style_plan(features, geofence_wgs84, template, style, scale_denominator)

    canvas = CairoCanvas()
    canvas.set_page(template.page_mm, bleed_mm=template.bleed_mm)
    font_id = canvas.embedded_font(DEFAULT_TTF_PATH)

    for prim in plan.primitives:
        canvas.path(prim.ops, prim.stroke, prim.fill)

    title_rect = template.furniture.get("title_block_mm")
    attr_rect = template.furniture.get("attribution_mm")
    glyphs: list[GlyphPlacement] = []
    if title_rect is not None:
        glyphs.append(
            GlyphPlacement(
                text=f"{area_name} Street Map - 1:{int(round(scale_denominator))}",
                x_mm=round(title_rect.x + 2.0, 3),
                y_mm=round(title_rect.y + title_rect.h * 0.65, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=3.5,
                color="#0f172a",
            )
        )
    if attr_rect is not None:
        glyphs.append(
            GlyphPlacement(
                text="Map data (c) OpenStreetMap contributors (ODbL)",
                x_mm=round(attr_rect.x + 1.0, 3),
                y_mm=round(attr_rect.y + attr_rect.h * 0.70, 3),
                angle_deg=0.0,
                font_id=font_id,
                size_mm=1.6,
                color="#334155",
            )
        )
    if glyphs:
        canvas.text(glyphs)

    pdf_path = out_dir / "proof.pdf"
    thumb_path = out_dir / "thumb.png"
    drawlog_path = out_dir / "drawlog.json"

    canvas.save_pdf(pdf_path)
    canvas.render_thumbnail(thumb_path, dpi=120)

    checks = verify_pdf_structure(pdf_path, expected_size_mm=template.page_mm)
    return ProofRenderOutput(
        pdf_path=pdf_path,
        thumb_path=thumb_path,
        drawlog_path=drawlog_path,
        pdf_sha256=sha256_hex(pdf_path.read_bytes()),
        thumb_sha256=sha256_hex(thumb_path.read_bytes()),
        content_hash=canvas.content_hash(),
        plan=plan,
        structural_checks=checks,
    )


def verify_pdf_structure(
    pdf_path: Path,
    expected_size_mm: tuple[float, float],
) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    if page_count < 1:
        raise ValueError("PDF must contain a page")
    page = reader.pages[0]
    mbox = page.mediabox
    w_pt = float(mbox.width)
    h_pt = float(mbox.height)
    exp_w_pt = expected_size_mm[0] * PT_PER_MM
    exp_h_pt = expected_size_mm[1] * PT_PER_MM
    page_size_matches = abs(w_pt - exp_w_pt) <= 1.0 and abs(h_pt - exp_h_pt) <= 1.0

    content = page.get_contents()
    stream = content.get_data().decode("latin-1", errors="replace") if content else ""
    # Decode graphic operations, including valid even-odd operators B* and f*.
    operators = [op for _args, op in ContentStream(content, reader).operations] if content else []
    has_vector_paths = bool(
        (
            any(op in (b"m", b"l", b"c", b"v", b"y", b"re") for op in operators)
            and any(op in (b"S", b"s", b"f", b"f*", b"F", b"B", b"B*", b"b", b"b*") for op in operators)
        )
        or (
            re.search(r"(?:^|\\s)(?:m|l|c|v|y|re)(?=\\s|$)", stream)
            and re.search(r"(?:^|\\s)(?:S|s|f\\*?|F|B\\*?|b\\*?)(?=\\s|$)", stream)
        )
    )

    resources = page["/Resources"].get_object()
    font_dict = resources.get("/Font")
    fonts = font_dict.get_object() if font_dict is not None else {}
    embedded_fonts = 0
    for font_obj in fonts.values():
        font = font_obj.get_object()
        descriptors = []
        if "/FontDescriptor" in font:
            descriptors.append(font["/FontDescriptor"].get_object())
        for descendant in font.get("/DescendantFonts", []):
            descendant_font = descendant.get_object()
            if "/FontDescriptor" in descendant_font:
                descriptors.append(descendant_font["/FontDescriptor"].get_object())
        for descriptor in descriptors:
            for key in ("/FontFile2", "/FontFile3", "/FontFile"):
                if key in descriptor and descriptor[key].get_object().get_data():
                    embedded_fonts += 1
                    break
    fonts_embedded = embedded_fonts > 0

    metadata = reader.metadata or {}
    has_odbl_attribution = "OpenStreetMap" in (
        str(metadata.get("/Subject", "")) + " " + stream
    ) and "ODbL" in (str(metadata.get("/Subject", "")) + " " + stream)

    xobjects = resources.get("/XObject")
    has_unexpected_raster = bool(
        xobjects and any(
            obj.get_object().get("/Subtype") == "/Image"
            for obj in xobjects.get_object().values()
        )
    )

    return {
        "page_count": page_count,
        "page_width_pt": round(w_pt, 3),
        "page_height_pt": round(h_pt, 3),
        "page_size_matches": page_size_matches,
        "has_vector_paths": has_vector_paths,
        "vector_path_operator_count": sum(op in (b"m", b"l", b"c", b"re") for op in operators),
        "vector_paint_operator_count": sum(op in (b"S", b"s", b"f", b"f*", b"B", b"B*") for op in operators),
        "fonts_embedded": fonts_embedded,
        "embedded_font_count": embedded_fonts,
        "has_odbl_attribution": has_odbl_attribution,
        "has_unexpected_raster": has_unexpected_raster,
    }
