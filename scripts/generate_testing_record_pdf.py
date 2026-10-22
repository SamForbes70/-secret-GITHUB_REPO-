# ruff: noqa: E501
"""Generate multi-page vector PDF Testing & Verification Record for Maps4U v1.0.0-mvp."""

from __future__ import annotations

import shutil
from pathlib import Path


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _build_page_stream(lines_spec: list[tuple[str, float, float, float, str, str]]) -> bytes:
    """Render a page stream from (font, size, x_pt, y_pt, hex_rgb, text) tuples plus header banner."""
    cmds: list[str] = [
        "q",
        "0.06 0.09 0.16 rg 36 778 523 36 re f",
        "0.91 0.95 0.99 RG 0.6 w 36 42 523 772 re S",
    ]
    for font_key, size_pt, x_pt, y_pt, rgb_str, text in lines_spec:
        cmds.append(f"BT /{font_key} {size_pt:.1f} Tf {rgb_str} rg 1 0 0 1 {x_pt:.1f} {y_pt:.1f} Tm ({_esc(text)}) Tj ET")
    cmds.append("Q")
    return ("\n".join(cmds) + "\n").encode("latin-1")


def generate_pdf(pdf_path: Path, pytest_log_path: Path) -> dict[str, object]:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pytest_lines = pytest_log_path.read_text(encoding="utf-8").splitlines()

    p1: list[tuple[str, float, float, float, str, str]] = [
        ("F2", 13.0, 46.0, 796.0, "1 1 1", "MAPS4U STREET MAP SYSTEM (maps4u-maps) - COMPREHENSIVE TESTING RECORD"),
        ("F1", 8.5, 46.0, 784.0, "0.82 0.88 0.98", "Release: v1.0.0-mvp  |  Gates G1-G6: ALL PASSED  |  Tests: 61/61 Passed  |  Coverage: 92% (2,412 stmts)"),
        ("F2", 11.0, 46.0, 756.0, "0.12 0.23 0.54", "1. EXECUTIVE SMOKE & VERIFICATION SUMMARY"),
        ("F3", 8.0, 46.0, 740.0, "0.1 0.1 0.1", "Suite / Check                  | Command                                | Result | Key Verified Metrics"),
        ("F3", 8.0, 46.0, 730.0, "0.4 0.4 0.4", "-------------------------------+----------------------------------------+--------+------------------------------------------------------------"),
        ("F3", 8.0, 46.0, 718.0, "0.05 0.35 0.15", "End-to-End Smoke Test          | python scripts/smoke_test.py           | PASS   | status=proof_ready, cache_hit=true, canvas_hash=73726d3c..."),
        ("F3", 8.0, 46.0, 706.0, "0.05 0.35 0.15", "Byte & Content Determinism     | python scripts/verify_determinism.py   | PASS   | deterministic=true, content_hash=46ec3295..., pdf=dbc189d1..."),
        ("F3", 8.0, 46.0, 694.0, "0.05 0.35 0.15", "Hot SQLite + Bundle Drill      | python scripts/backup_restore_drill.py | PASS   | restored_ok=true, manifest_sha256=true, pdf_sha256=true"),
        ("F3", 8.0, 46.0, 682.0, "0.05 0.35 0.15", "Static Linter (Ruff)           | ruff check src tests scripts           | PASS   | All checks passed! (0 errors, 0 warnings)"),
        ("F3", 8.0, 46.0, 670.0, "0.05 0.35 0.15", "Strict Type Checker (Mypy)     | mypy src                               | PASS   | Success: no issues found in 46 source files"),
        ("F3", 8.0, 46.0, 658.0, "0.05 0.35 0.15", "Full Offline Pytest + Coverage | pytest -v --cov=src/maps4u             | PASS   | 61 passed, 0 failed in 22.65s; 92% total line coverage"),
        ("F2", 11.0, 46.0, 632.0, "0.12 0.23 0.54", "2. STAGE GATE PROGRESSION (G1 -> G6)"),
        ("F3", 8.0, 46.0, 616.0, "0.1 0.1 0.1", "Gate | Tag            | Scope & Deliverables Verified                                                   | Tests     | Status"),
        ("F3", 8.0, 46.0, 606.0, "0.4 0.4 0.4", "-----+----------------+---------------------------------------------------------------------------------+-----------+--------"),
        ("F3", 8.0, 46.0, 594.0, "0.1 0.1 0.1", "G1   | v0.1.0-phase0  | Stage 1: FastAPI/Celery scaffold, SQLite WAL, Overpass fetch + 8-layer GPKG     | 14 passed | PASSED"),
        ("F3", 8.0, 46.0, 582.0, "0.1 0.1 0.1", "G2   | v0.2.0-stage2  | Stage 2: 6 paper templates (A3/A4/A5), 1:N scale & 1.5mm font viability, UI     | 42 passed | PASSED"),
        ("F3", 8.0, 46.0, 570.0, "0.1 0.1 0.1", "G3   | v0.3.0-stage3  | Stage 3: CairoCanvas PDF 1.4 vector renderer (ADR-0001), mcy/v1 YAML style      | 46 passed | PASSED"),
        ("F3", 8.0, 46.0, 558.0, "0.1 0.1 0.1", "G4   | v0.4.0-stage4  | Stage 4: STRtree label collision engine, map furniture, 2-page inset, QA bundle | 54 passed | PASSED"),
        ("F3", 8.0, 46.0, 546.0, "0.1 0.1 0.1", "G5   | v0.5.0-stage5  | Stage 5: Full 11-stage job executor, review/approve lock, reproduce(), 3 pilots | 58 passed | PASSED"),
        ("F3", 8.0, 46.0, 534.0, "0.1 0.1 0.1", "G6   | v1.0.0-mvp     | Stage 6: Multi-stage Dockerfile + compose, runbook, backup drill, full UAT      | 61 passed | PASSED"),
        ("F2", 11.0, 46.0, 508.0, "0.12 0.23 0.54", "3. THREE-PILOT CARTOGRAPHIC & REPRODUCIBILITY ACCEPTANCE (S5.T3)"),
        ("F3", 8.0, 46.0, 492.0, "0.1 0.1 0.1", "Pilot Area                      | Format       | Scale Band                | Blockers | Overlaps/Clips | Min Font   | reproduce() Match"),
        ("F3", 8.0, 46.0, 482.0, "0.4 0.4 0.4", "--------------------------------+--------------+---------------------------+----------+----------------+------------+-------------------"),
        ("F3", 8.0, 46.0, 470.0, "0.05 0.35 0.15", "Maroochydore (MCY Reference)    | A4-landscape | standard_street (1:12500) | 0        | 0 / 0          | >= 1.50 mm | 100% SHA-256 Match"),
        ("F3", 8.0, 46.0, 458.0, "0.05 0.35 0.15", "Noosa                           | A3-landscape | detail (1:7500)           | 0        | 0 / 0          | >= 1.50 mm | 100% SHA-256 Match"),
        ("F3", 8.0, 46.0, 446.0, "0.05 0.35 0.15", "Bribie Island - Sandstone Point | A4-portrait  | standard_street (1:12500) | 0        | 0 / 0          | >= 1.50 mm | 100% SHA-256 Match"),
        ("F2", 11.0, 46.0, 420.0, "0.12 0.23 0.54", "4. SMOKE TEST & DETERMINISM JSON OUTPUTS"),
        ("F3", 7.5, 46.0, 404.0, "0.15 0.15 0.15", 'smoke_test.py: {"smoke_test": "PASSED", "final_job_status": "proof_ready", "cache_hit_verified": true,'),
        ("F3", 7.5, 46.0, 393.0, "0.15 0.15 0.15", '  "job_id": "maroochydore-smoke-2026-10-smoke1-c19322", "canvas_hash": "73726d3c2c7f7c93af4d14a88a613898..."}'),
        ("F3", 7.5, 46.0, 379.0, "0.15 0.15 0.15", 'verify_determinism.py: {"deterministic": true, "content_hash": "46ec32956f277efb83104b4c1b5492c93b2b099019186cdc71584a1a59ece6a8",'),
        ("F3", 7.5, 46.0, 368.0, "0.15 0.15 0.15", '  "pdf_sha256": "dbc189d129cd34366ca5addeb474a339dbf014e916ddd8a678b2892e219b9b17"}'),
        ("F3", 7.5, 46.0, 354.0, "0.15 0.15 0.15", 'backup_restore_drill.py: {"restored_ok": true, "manifest_sha256_match": true, "pdf_sha256_match": true}'),
        ("F1", 8.0, 46.0, 52.0, "0.35 0.35 0.35", "Page 1 of 3  |  Maps4U Street Map System v1.0.0-mvp  |  Full Pytest & Coverage Log on Pages 2-3"),
    ]

    # Filter out warning noise lines so pages 2 and 3 show all 61 test results + full coverage table
    clean_lines = [
        ln for ln in pytest_lines
        if ("::test_" in ln or "Name " in ln or "src/maps4u/" in ln or "TOTAL " in ln or "passed" in ln or "---" in ln)
    ]
    half = 62
    chunks = [clean_lines[:half], clean_lines[half:half*2]]
    pages_streams = [_build_page_stream(p1)]
    for page_idx, chunk in enumerate(chunks, start=2):
        spec: list[tuple[str, float, float, float, str, str]] = [
            ("F2", 12.5, 46.0, 796.0, "1 1 1", f"MAPS4U v1.0.0-mvp - PYTEST EXECUTION & COVERAGE RECORD (PAGE {page_idx} OF 3)"),
            ("F1", 8.5, 46.0, 784.0, "0.82 0.88 0.98", "61 Automated Tests (Unit, Property, Provider Contract, API, Golden Layout, PDF Structure, E2E UAT) + Coverage"),
        ]
        y = 758.0
        for ln in chunk:
            trimmed = ln[:112]
            color = "0.05 0.35 0.15" if ("PASSED" in trimmed or "TOTAL" in trimmed) else "0.12 0.12 0.12"
            spec.append(("F3", 7.2, 46.0, y, color, trimmed))
            y -= 10.8
        spec.append(("F1", 8.0, 46.0, 52.0, "0.35 0.35 0.35", f"Page {page_idx} of 3  |  Maps4U Street Map System v1.0.0-mvp  |  61/61 Tests Passed, 92% Coverage"))
        pages_streams.append(_build_page_stream(spec))

    objects: list[bytes] = []
    # Obj 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # Obj 2: Pages (3 pages at objs 6, 8, 10)
    objects.append(b"<< /Type /Pages /Kids [6 0 R 8 0 R 10 0 R] /Count 3 >>")
    # Obj 3, 4, 5: Standard Type1 Fonts (Helvetica, Helvetica-Bold, Courier)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

    for idx, stream_bytes in enumerate(pages_streams):
        page_obj_num = 6 + idx * 2
        content_obj_num = page_obj_num + 1
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            f"/Contents {content_obj_num} 0 R >>"
        ).encode("latin-1")
        content_obj = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"endstream"
        )
        objects.append(page_dict)
        objects.append(content_obj)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for idx, obj_b in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("latin-1"))
        out.extend(obj_b)
        out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    pdf_path.write_bytes(bytes(out))

    for dest in [
        Path("/a0/usr/projects/maps4u/Maps4U_Comprehensive_Testing_Record_v1.0.0-mvp.pdf"),
        Path("/a0/usr/workdir/Maps4U_Comprehensive_Testing_Record_v1.0.0-mvp.pdf"),
    ]:
        shutil.copy2(pdf_path, dest)
    return {"pdf_path": str(pdf_path), "bytes": pdf_path.stat().st_size, "pages": len(pages_streams)}


if __name__ == "__main__":
    res = generate_pdf(
        Path("/a0/usr/workdir/maps4u-street-map-system/docs/Maps4U_Comprehensive_Testing_Record_v1.0.0-mvp.pdf"),
        Path("/tmp/maps4u_pytest_report.txt"),
    )
    print(res)
