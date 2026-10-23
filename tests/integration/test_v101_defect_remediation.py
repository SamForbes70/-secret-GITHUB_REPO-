"""Regression test suite for Maps4U v1.0.1 defect remediation (BUG-001 through BUG-015)."""

from __future__ import annotations

import json
import shutil
import threading
import time
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.core.config import PACKAGED_RESOURCES_DIR, Settings, resolve_resource_path
from maps4u.core.db import db_session, run_migrations
from maps4u.core.errors import E_QA_FAILED, E_STATE_ILLEGAL, E_STYLE_INVALID, Maps4UError
from maps4u.core.models import BBox
from maps4u.core.state import transition_job_state
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import lookup_cached_snapshot
from maps4u.geo.corrections import load_and_validate_corrections
from maps4u.geo.overpass import OverpassClient
from maps4u.layout.templates import load_paper_templates
from maps4u.render.cairo_canvas import CairoCanvas
from maps4u.render.proof_renderer import render_proof
from maps4u.render.style_engine import load_style_by_ref
from maps4u.worker.pipeline import PipelineRunner
from maps4u.worker.tasks import run_job_task

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_OVERPASS = REPO_ROOT / "tests" / "fixtures" / "overpass" / "mcy_sample.json"

MCY_GEOFENCE = {
    "type": "Polygon",
    "coordinates": [
        [
            [153.085, -26.660],
            [153.105, -26.660],
            [153.105, -26.645],
            [153.085, -26.645],
            [153.085, -26.660],
        ]
    ],
}


def _make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    data_dir = tmp_path / "var"
    defaults: dict[str, Any] = {
        "MAPS4U_DATA_DIR": data_dir,
        "MAPS4U_DB_PATH": data_dir / "db" / "maps4u.sqlite3",
        "MAPS4U_ARTIFACT_DIR": data_dir / "jobs",
        "MAPS4U_CACHE_DIR": data_dir / "osm_cache",
        "MAPS4U_OVERPASS_URL": f"file://{FIXTURE_OVERPASS}",
        "MAPS4U_QUEUE": "inline",
        "MAPS4U_ENV": "test",
    }
    defaults.update(overrides)
    s = Settings(**defaults)
    s.ensure_dirs()
    run_migrations(s.db_path)
    return s


# ---------------------------------------------------------------------------
# BUG-001: Runtime dependencies declared & ProofRenderer / CairoCanvas work
# ---------------------------------------------------------------------------
def test_bug001_runtime_dependencies_declared_and_pdf_render_works(tmp_path: Path) -> None:
    pyproject_data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(pyproject_data["project"]["dependencies"]).lower()
    required_pkgs = (
        "pypdf2", "pillow", "reportlab", "pycairo", "fastapi",
        "celery", "redis", "geopandas", "shapely", "pyproj",
    )
    for required_pkg in required_pkgs:
        assert required_pkg in deps, f"Missing runtime dependency in pyproject.toml: {required_pkg}"

    canvas = CairoCanvas()
    canvas.set_page((297.0, 210.0), bleed_mm=3.0)
    pdf_out = tmp_path / "cairo_check.pdf"
    canvas.save_pdf(pdf_out)
    assert pdf_out.is_file()
    assert pdf_out.read_bytes().startswith(b"%PDF-")
    assert render_proof is not None


# ---------------------------------------------------------------------------
# BUG-002: Production resource paths are installation-safe
# ---------------------------------------------------------------------------
def test_bug002_resource_paths_installation_safe_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Verify packaged resources exist inside src/maps4u/resources
    assert (PACKAGED_RESOURCES_DIR / "config" / "paper_templates.yaml").is_file()
    assert (PACKAGED_RESOURCES_DIR / "schemas" / "style.schema.json").is_file()
    assert (PACKAGED_RESOURCES_DIR / "schemas" / "corrections.schema.json").is_file()
    assert (PACKAGED_RESOURCES_DIR / "styles" / "mcy" / "v1" / "style.yaml").is_file()

    # Copy resources to an isolated directory outside the repository and chdir to tmp_path
    isolated_root = tmp_path / "isolated_install"
    shutil.copytree(PACKAGED_RESOURCES_DIR / "config", isolated_root / "config")
    shutil.copytree(PACKAGED_RESOURCES_DIR / "schemas", isolated_root / "schemas")
    shutil.copytree(PACKAGED_RESOURCES_DIR / "styles", isolated_root / "styles")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAPS4U_CONFIG_DIR", str(isolated_root / "config"))
    monkeypatch.setenv("MAPS4U_SCHEMA_DIR", str(isolated_root / "schemas"))
    monkeypatch.setenv("MAPS4U_STYLE_DIR", str(isolated_root / "styles"))

    tpls = load_paper_templates(resolve_resource_path("config/paper_templates.yaml"))
    assert "A4-landscape" in tpls

    style = load_style_by_ref(
        "mcy/v1",
        style_dir=isolated_root / "styles",
        schema_path=isolated_root / "schemas" / "style.schema.json",
    )
    assert style.style_ref == "mcy/v1"

    corr_file = REPO_ROOT / "tests" / "fixtures" / "corrections" / "valid_corrections.yaml"
    corr_data, _ = load_and_validate_corrections(
        corr_file,
        schema_path=isolated_root / "schemas" / "corrections.schema.json",
    )
    assert "corrections" in corr_data


# ---------------------------------------------------------------------------
# BUG-003: API operations enforce authentication & RBAC
# ---------------------------------------------------------------------------
def test_bug003_authentication_and_rbac_enforced(tmp_path: Path) -> None:
    # 1. Production mode without tokens configured fails closed (503)
    prod_unconfigured = _make_settings(tmp_path / "prod_noconf", MAPS4U_ENV="prod", MAPS4U_OPERATOR_TOKEN="")
    client_noconf = TestClient(create_app(prod_unconfigured))
    r_noconf = client_noconf.post("/api/projects", json={"area_name": "Maroochydore"})
    assert r_noconf.status_code == 503
    assert r_noconf.json()["error"]["code"] == "E_FORBIDDEN"

    # 2. Production mode with distinct operator and reviewer tokens
    op_token = "op-secret-token-123"
    rev_token = "rev-secret-token-456"
    settings = _make_settings(
        tmp_path / "prod_auth",
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN=op_token,
        MAPS4U_REVIEWER_TOKEN=rev_token,
    )
    client = TestClient(create_app(settings))

    # Anonymous requests are rejected with 401
    assert client.post("/api/projects", json={"area_name": "Maroochydore"}).status_code == 401
    viab_payload = {"geofence": MCY_GEOFENCE, "paper": "A4", "orientation": "landscape"}
    assert client.post("/api/viability", json=viab_payload).status_code == 401
    assert client.get("/api/jobs").status_code == 401

    # Invalid token rejected with 401
    bad_headers = {"Authorization": "Bearer wrong-token"}
    assert client.post("/api/projects", json={"area_name": "Maroochydore"}, headers=bad_headers).status_code == 401

    # Reviewer token cannot create projects or jobs (403)
    rev_headers = {"Authorization": f"Bearer {rev_token}", "X-Operator-Identity": "claire.reviewer"}
    assert client.post("/api/projects", json={"area_name": "Maroochydore"}, headers=rev_headers).status_code == 403

    # Operator token can create project, geofence, and job, and run pipeline
    op_headers = {"Authorization": f"Bearer {op_token}", "X-Operator-Identity": "sam.operator"}
    proj = client.post("/api/projects", json={"area_name": "Maroochydore"}, headers=op_headers)
    assert proj.status_code == 201
    pid = proj.json()["project_id"]

    rev = client.post(f"/api/projects/{pid}/geofence", json=MCY_GEOFENCE, headers=op_headers)
    assert rev.status_code == 201
    rid = rev.json()["revision_id"]

    job = client.post(
        "/api/jobs",
        json={"project_id": pid, "geofence_revision": rid, "paper": "A4", "orientation": "landscape", "edition": "auth1"},
        headers=op_headers,
    )
    assert job.status_code == 201
    jid = job.json()["job_id"]

    run_r = client.post(f"/api/jobs/{jid}/run", headers=op_headers)
    assert run_r.status_code == 200
    assert run_r.json()["status"] == "proof_ready"

    # Anonymous artifact access is rejected (401)
    assert client.get(f"/api/jobs/{jid}/artifacts/proof.pdf").status_code == 401
    assert client.get(f"/api/jobs/{jid}/artifacts/proof.pdf", headers=rev_headers).status_code == 200

    # Operator token cannot approve when dedicated reviewer token is configured (403)
    assert client.post(f"/api/jobs/{jid}/approve", json={"reviewer": "spoofed"}, headers=op_headers).status_code == 403

    # Reviewer token can approve, and authenticated identity overrides spoofed body reviewer
    app_r = client.post(f"/api/jobs/{jid}/approve", json={"reviewer": "spoofed_name", "comment": "LGTM"}, headers=rev_headers)
    assert app_r.status_code == 200
    assert app_r.json()["status"] == "finalized"
    assert app_r.json()["reviewer"] == "claire.reviewer"


# ---------------------------------------------------------------------------
# BUG-004: Celery worker task executes jobs when queue mode is celery
# ---------------------------------------------------------------------------
def test_bug004_celery_queue_mode_dispatches_and_worker_executes(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, MAPS4U_QUEUE="celery")
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Maroochydore Celery"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "celery1",
        },
    ).json()
    job_id = job["job_id"]

    dispatched_calls: list[tuple[Any, Any]] = []

    def _fake_apply_async(*, args: Any = None, kwargs: Any = None, **_rest: Any) -> Any:
        dispatched_calls.append((args, kwargs))

    with patch.object(run_job_task, "apply_async", side_effect=_fake_apply_async):
        run_resp = client.post(f"/api/jobs/{job_id}/run")
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "queued"
        assert len(dispatched_calls) == 1
        task_args, task_kwargs = dispatched_calls[0]
        assert task_args == [job_id]

    # Now invoke the actual Celery worker task function as the worker process does
    worker_result = run_job_task.run(job_id, settings_overrides=task_kwargs["settings_overrides"])
    assert worker_result["status"] == "proof_ready"
    assert len(worker_result["proof_sha256"]) == 64

    job_after = client.get(f"/api/jobs/{job_id}").json()
    assert job_after["status"] == "proof_ready"


# ---------------------------------------------------------------------------
# BUG-005: Redis environment variable standardised across Compose & Settings
# ---------------------------------------------------------------------------
def test_bug005_redis_env_var_standardised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS4U_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.delenv("REDIS_URL", raising=False)
    s1 = Settings(MAPS4U_DATA_DIR=tmp_path / "s1", MAPS4U_ENV="test")
    assert s1.redis_url == "redis://redis:6379/0"

    monkeypatch.delenv("MAPS4U_REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://custom-redis:6379/2")
    s2 = Settings(MAPS4U_DATA_DIR=tmp_path / "s2", MAPS4U_ENV="test")
    assert s2.redis_url == "redis://custom-redis:6379/2"

    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "MAPS4U_REDIS_URL:" in compose_text
    assert "redis://redis:6379/0" in compose_text


# ---------------------------------------------------------------------------
# BUG-006: Duplicate job submission rejected; finalised jobs never reset
# ---------------------------------------------------------------------------
def test_bug006_duplicate_submission_rejected_and_reproduce_endpoint(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Maroochydore"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    payload = {
        "project_id": proj["project_id"],
        "geofence_revision": rev["revision_id"],
        "paper": "A4",
        "orientation": "landscape",
        "edition": "dup-test-1",
    }
    j1 = client.post("/api/jobs", json=payload)
    assert j1.status_code == 201
    job_id = j1.json()["job_id"]

    # Duplicate in 'created' state -> 409 conflict
    dup1 = client.post("/api/jobs", json=payload)
    assert dup1.status_code == 409
    assert dup1.json()["error"]["code"] == E_STATE_ILLEGAL

    # Run to 'proof_ready'
    assert client.post(f"/api/jobs/{job_id}/run").status_code == 200
    # Duplicate in 'proof_ready' state -> 409 conflict
    dup2 = client.post("/api/jobs", json=payload)
    assert dup2.status_code == 409
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "proof_ready"

    # Approve to 'finalized'
    app_r = client.post(f"/api/jobs/{job_id}/approve", json={"reviewer": "qa_lead"})
    assert app_r.status_code == 200
    locked_sha = app_r.json()["proof_sha256"]

    # Duplicate in 'finalized' state -> 409 conflict, never resets status!
    dup3 = client.post("/api/jobs", json=payload)
    assert dup3.status_code == 409
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "finalized"

    # Intentional reproduction endpoint works on finalized job
    repro_r = client.post(f"/api/jobs/{job_id}/reproduce")
    assert repro_r.status_code == 200
    assert repro_r.json()["matched"] is True
    assert repro_r.json()["reproduced_pdf_sha256"] == locked_sha


# ---------------------------------------------------------------------------
# BUG-007: Geofence revision IDs are project-scoped; no cross-project collision
# ---------------------------------------------------------------------------
def test_bug007_geofence_revision_ids_scoped_per_project(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    p1 = client.post("/api/projects", json={"area_name": "Project Alpha"}).json()["project_id"]
    p2 = client.post("/api/projects", json={"area_name": "Project Beta"}).json()["project_id"]

    r1 = client.post(f"/api/projects/{p1}/geofence", json=MCY_GEOFENCE)
    r2 = client.post(f"/api/projects/{p2}/geofence", json=MCY_GEOFENCE)
    assert r1.status_code == 201
    assert r2.status_code == 201

    rev1 = r1.json()
    rev2 = r2.json()
    assert rev1["revision_id"] != rev2["revision_id"]
    assert rev1["geometry_sha256"] == rev2["geometry_sha256"]

    # Re-saving identical geometry in Project Alpha is idempotent
    r1_repeat = client.post(f"/api/projects/{p1}/geofence", json=MCY_GEOFENCE)
    assert r1_repeat.status_code == 201
    assert r1_repeat.json()["revision_id"] == rev1["revision_id"]

    # Project Alpha still owns its revision
    p1_revs = client.get(f"/api/projects/{p1}/revisions").json()
    p2_revs = client.get(f"/api/projects/{p2}/revisions").json()
    assert len(p1_revs) == 1 and p1_revs[0]["revision_id"] == rev1["revision_id"]
    assert len(p2_revs) == 1 and p2_revs[0]["revision_id"] == rev2["revision_id"]


# ---------------------------------------------------------------------------
# BUG-008: Failed QA or corrupted PDF blocks proof_ready and approval
# ---------------------------------------------------------------------------
def test_bug008_failed_qa_and_corrupted_pdf_block_proof_ready_and_approval(tmp_path: Path) -> None:
    # 1. Pipeline run with impossibly high min_font_mm (9.5mm) triggers QA blocker -> fails before proof_ready
    strict_settings = _make_settings(tmp_path / "strict", MAPS4U_MIN_FONT_MM=9.5)
    client_strict = TestClient(create_app(strict_settings))
    proj = client_strict.post("/api/projects", json={"area_name": "QA Fail Area"}).json()
    rev = client_strict.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job = client_strict.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "qafail1",
        },
    ).json()
    job_id = job["job_id"]

    run_r = client_strict.post(f"/api/jobs/{job_id}/run")
    assert run_r.status_code == 422
    assert run_r.json()["error"]["code"] == E_QA_FAILED

    job_state = client_strict.get(f"/api/jobs/{job_id}").json()
    assert job_state["status"] == "failed"
    assert job_state["error_code"] == E_QA_FAILED

    # Attempting to approve a failed job is rejected
    app_r = client_strict.post(f"/api/jobs/{job_id}/approve", json={"reviewer": "reviewer"})
    assert app_r.status_code == 409

    # 2. If a proof_ready job has its qa-report.json or proof.pdf corrupted prior to approval, approval is blocked
    ok_settings = _make_settings(tmp_path / "corrupt")
    client_ok = TestClient(create_app(ok_settings))
    p2 = client_ok.post("/api/projects", json={"area_name": "Maroochydore"}).json()
    r2 = client_ok.post(f"/api/projects/{p2['project_id']}/geofence", json=MCY_GEOFENCE).json()
    j2 = client_ok.post(
        "/api/jobs",
        json={
            "project_id": p2["project_id"],
            "geofence_revision": r2["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "corrupt1",
        },
    ).json()["job_id"]
    assert client_ok.post(f"/api/jobs/{j2}/run").status_code == 200

    # Corrupt proof.pdf on disk -> approval must fail with E_QA_FAILED
    pdf_path = ok_settings.artifact_dir / j2 / "proof.pdf"
    orig_bytes = pdf_path.read_bytes()
    pdf_path.write_bytes(b"NOT-A-VALID-PDF")
    bad_app = client_ok.post(f"/api/jobs/{j2}/approve", json={"reviewer": "reviewer"})
    assert bad_app.status_code == 422
    assert bad_app.json()["error"]["code"] == E_QA_FAILED

    # Restore proof.pdf, corrupt qa-report.json to passed=False -> approval must fail with E_QA_FAILED
    pdf_path.write_bytes(orig_bytes)
    qa_path = ok_settings.artifact_dir / j2 / "qa-report.json"
    qa_data = json.loads(qa_path.read_text(encoding="utf-8"))
    qa_data["passed"] = False
    qa_data["blocker_count"] = 1
    qa_path.write_text(json.dumps(qa_data), encoding="utf-8")
    bad_app2 = client_ok.post(f"/api/jobs/{j2}/approve", json={"reviewer": "reviewer"})
    assert bad_app2.status_code == 422
    assert bad_app2.json()["error"]["code"] == E_QA_FAILED


# ---------------------------------------------------------------------------
# BUG-009: Unexpected pipeline exceptions transition to failed & allow retry
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fail_stage", ["acquiring", "rendering", "verifying"])
def test_bug009_unexpected_pipeline_exceptions_transition_to_failed_and_retry(
    tmp_path: Path, fail_stage: str
) -> None:
    settings = _make_settings(tmp_path / fail_stage)
    job_id = f"job-fail-{fail_stage}"
    with db_session(settings.db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, area_name, geofence_geojson, paper, orientation, style_ref, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'created')",
            (job_id, "TestArea", json.dumps(MCY_GEOFENCE), "A4", "landscape", "mcy/v1"),
        )

    def _ok(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _boom(_jid: str, _ctx: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"Simulated unexpected crash at {fail_stage}")

    all_stages = [
        ("validating", _ok),
        ("queued", _ok),
        ("assessing", _ok),
        ("acquiring", _boom if fail_stage == "acquiring" else _ok),
        ("transforming", _ok),
        ("styling", _ok),
        ("labelling", _ok),
        ("composing", _ok),
        ("rendering", _boom if fail_stage == "rendering" else _ok),
        ("verifying", _boom if fail_stage == "verifying" else _ok),
    ]
    runner = PipelineRunner(settings)
    with pytest.raises(Maps4UError) as exc_info:
        runner.run_stages(job_id, all_stages)
    assert exc_info.value.code == "E_PIPELINE_FAILED"
    assert exc_info.value.details["stage"] == fail_stage
    assert exc_info.value.details["exception_type"] == "RuntimeError"

    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT status, error_code, error_detail FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        assert row["status"] == "failed"
        assert row["error_code"] == "E_PIPELINE_FAILED"
        assert fail_stage in row["error_detail"]
        # Controlled retry transitions failed -> queued cleanly
        new_st = transition_job_state(
            conn,
            job_id=job_id,
            target_state="queued",
            stage="queued",
            event="retry_after_crash",
            data_dir=settings.maps4u_data_dir,
            artifact_dir=settings.artifact_dir,
        )
        assert new_st == "queued"


# ---------------------------------------------------------------------------
# BUG-011 & BUG-012: Makefile syntax & Settings lowercase/uppercase support
# ---------------------------------------------------------------------------
def test_bug011_and_bug012_makefile_and_settings_field_names(tmp_path: Path) -> None:
    makefile_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\t$(PYTHON) -m uvicorn maps4u.api.main:create_app --factory" in makefile_text

    s_lower = Settings(
        maps4u_data_dir=tmp_path / "lower",
        maps4u_db_path=tmp_path / "lower" / "m.db",
        maps4u_env="test",
    )
    assert s_lower.db_path == tmp_path / "lower" / "m.db"


# ---------------------------------------------------------------------------
# BUG-013: Style selection validation and custom render settings
# ---------------------------------------------------------------------------
def test_bug013_style_selection_validation_and_custom_style_manifest(tmp_path: Path) -> None:
    custom_styles_dir = tmp_path / "custom_styles"
    shutil.copytree(REPO_ROOT / "styles" / "mcy" / "v1", custom_styles_dir / "mcy" / "v1")
    shutil.copytree(REPO_ROOT / "styles" / "mcy" / "v1", custom_styles_dir / "sunshine" / "v2")

    alt_yaml_path = custom_styles_dir / "sunshine" / "v2" / "style.yaml"
    alt_data = yaml.safe_load(alt_yaml_path.read_text(encoding="utf-8"))
    alt_data["meta"]["style_ref"] = "sunshine/v2"
    alt_yaml_path.write_text(yaml.safe_dump(alt_data), encoding="utf-8")

    settings = _make_settings(
        tmp_path,
        MAPS4U_STYLE_DIR=custom_styles_dir,
        MAPS4U_INSETS_ENABLED=False,
    )
    client = TestClient(create_app(settings))

    # Unknown style_ref is rejected with 422 E_STYLE_INVALID
    bad_viab = client.post(
        "/api/viability",
        json={"geofence": MCY_GEOFENCE, "paper": "A4", "orientation": "landscape", "style_ref": "unknown/v9"},
    )
    assert bad_viab.status_code == 422
    assert bad_viab.json()["error"]["code"] == E_STYLE_INVALID

    proj = client.post("/api/projects", json={"area_name": "Sunshine"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()

    bad_job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "style_ref": "unknown/v9",
        },
    )
    assert bad_job.status_code == 422
    assert bad_job.json()["error"]["code"] == E_STYLE_INVALID

    # Valid alternative style_ref 'sunshine/v2' is used and recorded in manifest.json
    good_job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "style_ref": "sunshine/v2",
            "edition": "alt1",
        },
    )
    assert good_job.status_code == 201
    jid = good_job.json()["job_id"]
    assert client.post(f"/api/jobs/{jid}/run").status_code == 200

    manifest = client.get(f"/api/jobs/{jid}/artifacts/manifest.json").json()
    assert manifest["provenance"]["style_ref"] == "sunshine/v2"
    expected_alt_style = load_style_by_ref("sunshine/v2", style_dir=custom_styles_dir)
    assert manifest["provenance"]["style_sha256"] == expected_alt_style.sha256


# ---------------------------------------------------------------------------
# BUG-014: Browser interface completes full operator journey
# ---------------------------------------------------------------------------
def test_bug014_browser_ui_complete_operator_journey(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    html = client.get("/").text
    for control_id in (
        "auth-token",
        "operator-identity",
        "error-banner",
        "btn-run-job",
        "btn-refresh-job",
        "btn-reproduce-job",
        "btn-approve-job",
        "btn-reject-job",
        "btn-submit-corrections",
        "artifact-links",
    ):
        assert control_id in html, f"Missing browser UI element #{control_id}"

    js = client.get("/static/app.js").text
    for endpoint_fragment in ("/run", "/reproduce", "/approve", "/reject", "/corrections", "/artifacts/"):
        assert endpoint_fragment in js, f"Missing endpoint integration {endpoint_fragment} in app.js"


# ---------------------------------------------------------------------------
# BUG-015: Overpass concurrency, cache TTL ageing, and post-approval tamper check
# ---------------------------------------------------------------------------
def test_bug015_overpass_concurrency_cache_ttl_and_artifact_tamper_detection(tmp_path: Path) -> None:
    # 1. Overpass concurrency limit enforcement
    active_calls = 0
    max_observed = 0
    lock = threading.Lock()

    def _slow_transport(_url: str, _q: str) -> bytes:
        nonlocal active_calls, max_observed
        with lock:
            active_calls += 1
            max_observed = max(max_observed, active_calls)
        time.sleep(0.05)
        with lock:
            active_calls -= 1
        return FIXTURE_OVERPASS.read_bytes()

    ov_client = OverpassClient("https://example.invalid/overpass", transport=_slow_transport, max_concurrency=1)
    threads = [threading.Thread(target=lambda: ov_client.fetch_raw("q")) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_observed == 1

    # 2. Cache TTL ageing enforcement
    settings = _make_settings(tmp_path, MAPS4U_CACHE_MAX_AGE_DAYS=1)
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    ext1 = get_or_fetch(bbox=bbox, classes=classes, settings=settings)
    assert ext1.cache_hit is False

    # Age the snapshot in SQLite to 5 days ago -> lookup_cached_snapshot must expire it
    five_days_ago = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    with db_session(settings.db_path) as conn:
        conn.execute("UPDATE osm_snapshots SET fetched_at = ? WHERE snapshot_id = ?", (five_days_ago, ext1.snapshot_id))
    expired = lookup_cached_snapshot(settings.db_path, settings.cache_dir, ext1.snapshot_id, ext1.query, max_age_days=1)
    assert expired is None
    ext2 = get_or_fetch(bbox=bbox, classes=classes, settings=settings)
    assert ext2.cache_hit is False

    # 3. Artifact download detects post-approval tampering
    client = TestClient(create_app(settings))
    proj = client.post("/api/projects", json={"area_name": "Tamper Check"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "tamper1",
        },
    ).json()["job_id"]
    assert client.post(f"/api/jobs/{job}/run").status_code == 200
    assert client.post(f"/api/jobs/{job}/approve", json={"reviewer": "auditor"}).status_code == 200

    # Valid download succeeds
    assert client.get(f"/api/jobs/{job}/artifacts/proof.pdf").status_code == 200

    # Tamper with proof.pdf after approval -> download must fail with 409 E_STORAGE
    pdf_path = settings.artifact_dir / job / "proof.pdf"
    pdf_path.write_bytes(pdf_path.read_bytes() + b"\n%tampered")
    tampered_resp = client.get(f"/api/jobs/{job}/artifacts/proof.pdf")
    assert tampered_resp.status_code == 409
    assert tampered_resp.json()["error"]["code"] == "E_STORAGE"
