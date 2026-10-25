"""v1.0.5 release-blocker regression tests with real API and PDF assertions."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PyPDF2 import PdfReader

from maps4u import __version__
from maps4u.api.main import create_app
from maps4u.core.config import Settings
from maps4u.render.cairo_canvas import CairoCanvas, DEFAULT_TTF_PATH
from maps4u.render.canvas import Fill, GlyphPlacement, PathOps, Stroke
from maps4u.render.proof_renderer import verify_pdf_structure

GEO = {
    "type": "Polygon",
    "coordinates": [[
        [153.085, -26.660], [153.105, -26.660],
        [153.105, -26.645], [153.085, -26.645], [153.085, -26.660],
    ]],
}


def test_v105_version_consistent_with_installed_distribution() -> None:
    assert version("maps4u") == __version__
    assert __version__ == "1.0.5"


def test_v105_pdf_contains_real_embedded_font_and_unicode(tmp_path: Path) -> None:
    canvas = CairoCanvas()
    canvas.set_page((297.0, 210.0), bleed_mm=3.0)
    font_id = canvas.embedded_font(DEFAULT_TTF_PATH)
    canvas.path(
        PathOps([("M", (10, 10)), ("L", (60, 10)), ("L", (60, 40)), ("Z", ())]),
        Stroke("#444444", 0.2),
        Fill("#eeeeee"),
    )
    canvas.text([
        GlyphPlacement("München Straße Ångström", 20.0, 30.0, 0.0, font_id, 3.0, "#222222"),
    ])
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    canvas.save_pdf(pdf_a)
    canvas.save_pdf(pdf_b)
    assert pdf_a.read_bytes() == pdf_b.read_bytes()
    checks = verify_pdf_structure(pdf_a, (297.0, 210.0))
    assert checks["fonts_embedded"] is True
    assert checks["embedded_font_count"] >= 1
    assert checks["has_vector_paths"] is True
    reader = PdfReader(str(pdf_a))
    fonts = reader.pages[0]["/Resources"]["/Font"].get_object()
    descriptors = [
        font.get_object()["/FontDescriptor"].get_object()
        for font in fonts.values()
        if "/FontDescriptor" in font.get_object()
    ]
    assert any("/FontFile2" in d and d["/FontFile2"].get_object().get_data() for d in descriptors)


def _client(tmp_path: Path, queue: str = "inline") -> TestClient:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "overpass" / "mcy_sample.json"
    settings = Settings(
        MAPS4U_ENV="test",
        MAPS4U_QUEUE=queue,
        MAPS4U_DATA_DIR=tmp_path / "var",
        MAPS4U_OVERPASS_URL=f"file://{fixture}",
    )
    return TestClient(create_app(settings))


def _project_job(client: TestClient) -> str:
    project = client.post("/api/projects", json={"area_name": "v105 test"}).json()
    rev = client.post(f"/api/projects/{project['project_id']}/geofence", json=GEO).json()
    r = client.post("/api/jobs", json={
        "project_id": project["project_id"],
        "geofence_revision": rev["revision_id"],
        "paper": "A4", "orientation": "landscape", "edition": "regression",
    })
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def test_v105_dispatch_failure_is_recoverable(tmp_path: Path) -> None:
    client = _client(tmp_path, queue="celery")
    job_id = _project_job(client)
    with patch("maps4u.api.routes_jobs.run_job_task.apply_async", side_effect=OSError("broker unavailable")):
        response = client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 503, response.text
    row = client.get(f"/api/jobs/{job_id}").json()
    assert row["status"] == "failed"
    assert row["error_code"] == "E_QUEUE_UNAVAILABLE"
    with patch("maps4u.api.routes_jobs.run_job_task.apply_async") as mock_dispatch:
        retry = client.post(f"/api/jobs/{job_id}/run")
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "queued"
    mock_dispatch.assert_called_once()


def test_v105_invalid_corrections_leave_no_orphan_files(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _project_job(client)
    for yaml_text in ("invalid: [", "not_a_corrections_file: true"):
        response = client.post(f"/api/jobs/{job_id}/corrections", json={
            "yaml_content": yaml_text,
            "author": "tester",
        })
        assert response.status_code == 422, response.text
    correction_dir = tmp_path / "var" / "corrections"
    assert not list(correction_dir.glob("*.yaml"))
