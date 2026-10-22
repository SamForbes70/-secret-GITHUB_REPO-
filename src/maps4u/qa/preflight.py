"""QA preflight engine and Markdown + JSON report generators (Stage 4 S4.T3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import box

from maps4u.geo.features import FeatureSet
from maps4u.labels.engine import LabelResult
from maps4u.layout.furniture import ComposedLayout
from maps4u.layout.templates import PaperTemplate
from maps4u.render.proof_renderer import verify_pdf_structure
from maps4u.render.style_engine import DrawPlan, LoadedStyle


@dataclass(frozen=True)
class QaFinding:
    rule: str
    severity: str  # blocker | warning | info
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QaReport:
    job_id: str
    passed: bool
    blocker_count: int
    warning_count: int
    info_count: int
    min_font_mm_observed: float
    min_font_ok: bool
    overlaps: int
    clipped: int
    dropped_count: int
    findings: list[QaFinding] = field(default_factory=list)
    structural_checks: dict[str, Any] = field(default_factory=dict)
    report_json_path: Path | None = None
    report_md_path: Path | None = None


def run_qa(
    job_id: str,
    pdf_path: Path,
    template: PaperTemplate,
    style: LoadedStyle,
    plan: DrawPlan,
    labels: LabelResult,
    composed: ComposedLayout,
    features: FeatureSet,
    out_dir: Path,
    min_font_threshold_mm: float = 1.5,
) -> QaReport:
    del style, features
    out_dir.mkdir(parents=True, exist_ok=True)
    findings: list[QaFinding] = []

    # 1. PDF structure checks
    struct_checks = verify_pdf_structure(pdf_path, expected_size_mm=template.page_mm)
    if not struct_checks.get("page_size_matches", False):
        findings.append(
            QaFinding(
                rule="PDF_PAGE_SIZE",
                severity="blocker",
                message="Rendered PDF MediaBox does not match template page dimensions.",
                evidence=struct_checks,
            )
        )
    if not struct_checks.get("has_vector_paths", False):
        findings.append(
            QaFinding(
                rule="PDF_VECTOR_PATHS",
                severity="blocker",
                message="Rendered PDF contains no vector path operators.",
                evidence=struct_checks,
            )
        )
    if not struct_checks.get("fonts_embedded", False):
        findings.append(
            QaFinding(
                rule="PDF_FONTS_EMBEDDED",
                severity="blocker",
                message="Rendered PDF does not embed TrueType font descriptors.",
                evidence=struct_checks,
            )
        )
    if not struct_checks.get("has_odbl_attribution", False) or not composed.has_attribution:
        findings.append(
            QaFinding(
                rule="ODBL_ATTRIBUTION",
                severity="blocker",
                message="Mandatory OpenStreetMap ODbL attribution is missing.",
                evidence=struct_checks,
            )
        )
    if struct_checks.get("has_unexpected_raster", False):
        findings.append(
            QaFinding(
                rule="PDF_NO_RASTER_TILES",
                severity="blocker",
                message="Unexpected raster image stream detected in vector map PDF.",
                evidence=struct_checks,
            )
        )

    # 2. Empty map detection
    road_prims = [p for p in plan.primitives if p.layer == "roads"]
    if not road_prims:
        findings.append(
            QaFinding(
                rule="EMPTY_MAP_ROADS",
                severity="blocker",
                message="DrawPlan contains zero road primitives.",
                evidence={"primitive_count": len(plan.primitives)},
            )
        )

    # 3. Minimum font height, label overlaps, and frame clipping checks
    map_rect = template.map_area_mm
    min_observed = min((p.size_mm for p in labels.placed), default=min_font_threshold_mm)
    min_font_ok = True
    overlaps = 0
    clipped = 0
    placed_boxes: list[tuple[str, Any]] = []

    for pl in labels.placed:
        if pl.size_mm < min_font_threshold_mm - 1e-6:
            min_font_ok = False
            findings.append(
                QaFinding(
                    rule="MIN_FONT_HEIGHT",
                    severity="blocker",
                    message=f"Label '{pl.text}' font height {pl.size_mm} mm is below {min_font_threshold_mm} mm floor.",
                    evidence={"text": pl.text, "size_mm": pl.size_mm, "osm_id": pl.osm_id},
                )
            )
        if (
            pl.x_mm < map_rect.x - 0.05
            or pl.y_mm < map_rect.y - 0.05
            or (pl.x_mm + pl.w_mm) > (map_rect.right + 0.05)
            or (pl.y_mm + pl.h_mm) > (map_rect.bottom + 0.05)
        ):
            clipped += 1
            findings.append(
                QaFinding(
                    rule="LABEL_CLIPPED",
                    severity="blocker",
                    message=f"Label '{pl.text}' extends outside usable map frame.",
                    evidence={"text": pl.text, "x_mm": pl.x_mm, "y_mm": pl.y_mm, "w_mm": pl.w_mm, "h_mm": pl.h_mm},
                )
            )
        b = box(pl.x_mm, pl.y_mm, pl.x_mm + pl.w_mm, pl.y_mm + pl.h_mm)
        for prev_text, prev_box in placed_boxes:
            if b.intersects(prev_box):
                overlaps += 1
                findings.append(
                    QaFinding(
                        rule="LABEL_COLLISION",
                        severity="blocker",
                        message=f"Placed label '{pl.text}' overlaps with '{prev_text}'.",
                        evidence={"label_a": pl.text, "label_b": prev_text},
                    )
                )
        placed_boxes.append((pl.text, b))

    # 4. Dropped label warnings
    if labels.dropped:
        findings.append(
            QaFinding(
                rule="DROPPED_LABELS",
                severity="warning",
                message=f"{len(labels.dropped)} candidate label(s) were omitted due to space or length constraints.",
                evidence={
                    "dropped": [
                        {"text": d.text, "class": d.feature_class, "reason": d.reason}
                        for d in labels.dropped
                    ]
                },
            )
        )

    findings.append(
        QaFinding(
            rule="FURNITURE_SUMMARY",
            severity="info",
            message=f"Composed {composed.template_key} ({len(composed.street_index)} index entries).",
            evidence={"page_count": composed.page_count, "legend_classes": composed.legend_classes},
        )
    )

    blocker_count = sum(1 for f in findings if f.severity == "blocker")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    info_count = sum(1 for f in findings if f.severity == "info")
    passed = blocker_count == 0

    report_json_path = out_dir / "qa-report.json"
    report_md_path = out_dir / "qa-report.md"

    payload = {
        "job_id": job_id,
        "passed": passed,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "min_font_mm_observed": round(min_observed, 3),
        "min_font_ok": min_font_ok,
        "overlaps": overlaps,
        "clipped": clipped,
        "dropped_count": len(labels.dropped),
        "structural_checks": struct_checks,
        "findings": [asdict(f) for f in findings],
    }
    report_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    md_lines = [
        f"# Maps4U QA Preflight Report — `{job_id}`",
        "",
        f"- **Verdict:** {'PASS' if passed else 'FAIL (BLOCKED)'}",
        f"- **Blockers:** {blocker_count} | **Warnings:** {warning_count} | **Info:** {info_count}",
        f"- **Minimum Printed Font Height:** {min_observed:.2f} mm (floor: {min_font_threshold_mm:.2f} mm)",
        f"- **Placed Labels:** {len(labels.placed)} | **Dropped Labels:** {len(labels.dropped)}",
        f"- **Overlaps:** {overlaps} | **Clipped:** {clipped}",
        "",
        "## Findings",
        "",
        "| Severity | Rule | Message |",
        "|---|---|---|",
    ]
    for f in findings:
        md_lines.append(f"| `{f.severity.upper()}` | `{f.rule}` | {f.message} |")
    report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return QaReport(
        job_id=job_id,
        passed=passed,
        blocker_count=blocker_count,
        warning_count=warning_count,
        info_count=info_count,
        min_font_mm_observed=round(min_observed, 3),
        min_font_ok=min_font_ok,
        overlaps=overlaps,
        clipped=clipped,
        dropped_count=len(labels.dropped),
        findings=findings,
        structural_checks=struct_checks,
        report_json_path=report_json_path,
        report_md_path=report_md_path,
    )
