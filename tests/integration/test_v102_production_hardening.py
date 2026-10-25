"""Regression test suite for Maps4U v1.0.2 production hardening (SEC-001..003, DATA-001..003, QUEUE-001..003)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from maps4u.api.main import create_app
from maps4u.bundle.archive import reproduce
from maps4u.core.config import Settings
from maps4u.core.db import db_session, run_migrations
from maps4u.core.errors import (
    E_FORBIDDEN,
    E_OVERPASS_UNAVAILABLE,
    E_QA_FAILED,
    E_STATE_ILLEGAL,
    E_STORAGE,
    E_UNAUTHORIZED,
    Maps4UError,
)
from maps4u.core.models import BBox
from maps4u.core.state import GOVERNED_OUTPUT_FILES, release_job_claim, transition_job_state, try_acquire_job_claim
from maps4u.geo.acquire import get_or_fetch
from maps4u.geo.cache import read_geopackage_snapshot
from maps4u.worker.executor import execute_job_pipeline
from maps4u.worker.tasks import run_job_task

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_OVERPASS = REPO_ROOT / "tests" / "fixtures" / "overpass" / "mcy_sample.json"

MCY_GEOFENCE: dict[str, Any] = {
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
        "MAPS4U_CACHE_DIR": data_dir / "cache" / "osm",
        "MAPS4U_ARTIFACT_DIR": data_dir / "jobs",
        "MAPS4U_OVERPASS_URL": f"file://{FIXTURE_OVERPASS}",
        "MAPS4U_ENV": "test",
        "MAPS4U_QUEUE": "inline",
    }
    defaults.update(overrides)
    s = Settings(**defaults)
    s.ensure_dirs()
    run_migrations(s.db_path)
    return s


def test_sec001_production_rejects_missing_weak_or_known_fallback_credentials(tmp_path: Path) -> None:
    """SEC-001: Docker Compose has no public fallback token; prod rejects missing, weak, or fallback tokens."""
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "change-me-in-production" not in compose_text
    assert "MAPS4U_OPERATOR_TOKEN:?" in compose_text
    assert "MAPS4U_REVIEWER_TOKEN:?" in compose_text

    # 1. Known fallback token rejected in prod (503)
    s_fallback = _make_settings(
        tmp_path / "fallback",
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN="change-me-in-production",
        MAPS4U_REVIEWER_TOKEN="valid-reviewer-secret-token-999",
    )
    c_fallback = TestClient(create_app(s_fallback))
    r_fb = c_fallback.post(
        "/api/projects",
        json={"area_name": "Test"},
        headers={"Authorization": "Bearer change-me-in-production"},
    )
    assert r_fb.status_code == 503
    assert r_fb.json()["error"]["code"] == E_FORBIDDEN

    # 2. Short/weak token (<16 chars) rejected in prod (503)
    s_short = _make_settings(
        tmp_path / "short",
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN="short-token",
        MAPS4U_REVIEWER_TOKEN="valid-reviewer-secret-token-999",
    )
    c_short = TestClient(create_app(s_short))
    r_sh = c_short.post(
        "/api/projects",
        json={"area_name": "Test"},
        headers={"Authorization": "Bearer short-token"},
    )
    assert r_sh.status_code == 503

    # 3. Missing reviewer token or identical operator/reviewer token rejected in prod (503)
    same_tok = "shared-production-token-123456"
    s_same = _make_settings(
        tmp_path / "same",
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN=same_tok,
        MAPS4U_REVIEWER_TOKEN=same_tok,
    )
    c_same = TestClient(create_app(s_same))
    r_sm = c_same.post(
        "/api/projects",
        json={"area_name": "Test"},
        headers={"Authorization": f"Bearer {same_tok}"},
    )
    assert r_sm.status_code == 503


def test_sec002_verified_reviewer_identities_cannot_be_forged(tmp_path: Path) -> None:
    """SEC-002: X-Operator-Identity and request-body reviewer strings cannot forge authenticated reviewer identity."""
    op_tok = "prod-operator-token-abc123456789"
    rev_tok = "prod-reviewer-token-xyz987654321"
    settings = _make_settings(
        tmp_path,
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN=op_tok,
        MAPS4U_REVIEWER_TOKEN=rev_tok,
    )
    client = TestClient(create_app(settings))

    op_headers = {
        "Authorization": f"Bearer {op_tok}",
        "X-Operator-Identity": "forged.ceo.identity",
    }
    rev_headers = {
        "Authorization": f"Bearer {rev_tok}",
        "X-Operator-Identity": "forged.auditor.identity",
    }

    proj = client.post("/api/projects", json={"area_name": "SEC002 Area"}, headers=op_headers).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE, headers=op_headers).json()
    # Geofence created_by must be bound to operator credential fingerprint, not 'forged.ceo.identity'
    assert rev["created_by"].startswith("operator:")
    assert rev["created_by"] != "forged.ceo.identity"

    job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "sec002",
        },
        headers=op_headers,
    ).json()
    jid = job["job_id"]
    assert client.post(f"/api/jobs/{jid}/run", headers=op_headers).status_code == 200

    # Approve attempting both header forgery and request-body forgery
    app_resp = client.post(
        f"/api/jobs/{jid}/approve",
        json={"reviewer": "forged.body.reviewer", "comment": "Approved"},
        headers=rev_headers,
    )
    assert app_resp.status_code == 200
    recorded_reviewer = app_resp.json()["reviewer"]
    assert recorded_reviewer.startswith("reviewer:")
    assert recorded_reviewer not in ("forged.auditor.identity", "forged.body.reviewer")


def test_sec003_url_query_string_authentication_removed(tmp_path: Path) -> None:
    """SEC-003: Query-string ?token= bearer authentication is rejected on all endpoints and removed from UI."""
    op_tok = "prod-operator-token-abc123456789"
    rev_tok = "prod-reviewer-token-xyz987654321"
    settings = _make_settings(
        tmp_path,
        MAPS4U_ENV="prod",
        MAPS4U_OPERATOR_TOKEN=op_tok,
        MAPS4U_REVIEWER_TOKEN=rev_tok,
    )
    client = TestClient(create_app(settings))
    op_headers = {"Authorization": f"Bearer {op_tok}"}

    proj = client.post("/api/projects", json={"area_name": "SEC003 Area"}, headers=op_headers).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE, headers=op_headers).json()
    job = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "sec003",
        },
        headers=op_headers,
    ).json()
    jid = job["job_id"]
    assert client.post(f"/api/jobs/{jid}/run", headers=op_headers).status_code == 200

    # Query-string token must be rejected with 401
    q_resp = client.get(f"/api/jobs/{jid}/artifacts/proof.pdf?token={op_tok}")
    assert q_resp.status_code == 401
    assert q_resp.json()["error"]["code"] == E_UNAUTHORIZED

    # Header auth succeeds
    h_resp = client.get(f"/api/jobs/{jid}/artifacts/proof.pdf", headers=op_headers)
    assert h_resp.status_code == 200

    # Static UI JS must not append ?token= to URLs
    app_js = (REPO_ROOT / "src" / "maps4u" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "?token=" not in app_js


def test_data001_immutable_osm_provenance_across_cache_refreshes(tmp_path: Path) -> None:
    """DATA-001: Changed OSM data creates distinct immutable snapshots; approved jobs still reproduce."""
    fixture_v1 = tmp_path / "overpass_v1.json"
    fixture_v2 = tmp_path / "overpass_v2.json"
    raw_v1 = json.loads(FIXTURE_OVERPASS.read_text(encoding="utf-8"))
    raw_v2 = json.loads(FIXTURE_OVERPASS.read_text(encoding="utf-8"))
    raw_v2["osm3s"]["timestamp_osm_base"] = "2026-10-25T00:00:00Z"
    raw_v2["elements"].append(
        {
            "type": "node",
            "id": 99999901,
            "lat": -26.652,
            "lon": 153.095,
            "tags": {"name": "New Landmark V2", "tourism": "attraction"},
        }
    )
    fixture_v1.write_text(json.dumps(raw_v1), encoding="utf-8")
    fixture_v2.write_text(json.dumps(raw_v2), encoding="utf-8")

    settings = _make_settings(
        tmp_path,
        MAPS4U_OVERPASS_URL=f"file://{fixture_v1}",
        MAPS4U_CACHE_MAX_AGE_DAYS=-1,
    )
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Maroochydore Immutable"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job1 = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "imm-v1",
        },
    ).json()["job_id"]
    assert client.post(f"/api/jobs/{job1}/run").status_code == 200
    assert client.post(f"/api/jobs/{job1}/approve", json={"reviewer": "rev1"}).status_code == 200

    manifest1 = json.loads((settings.artifact_dir / job1 / "manifest.json").read_text(encoding="utf-8"))
    snap1_id = manifest1["provenance"]["snapshot_id"]
    snap1_sha = manifest1["provenance"]["snapshot_sha256"]

    # Switch upstream OSM data to v2 for the exact same BBox/geofence and run job2
    settings.maps4u_overpass_url = f"file://{fixture_v2}"
    job2 = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "imm-v2",
        },
    ).json()["job_id"]
    assert client.post(f"/api/jobs/{job2}/run").status_code == 200

    manifest2 = json.loads((settings.artifact_dir / job2 / "manifest.json").read_text(encoding="utf-8"))
    snap2_id = manifest2["provenance"]["snapshot_id"]
    snap2_sha = manifest2["provenance"]["snapshot_sha256"]

    # Distinct immutable snapshot IDs and files exist side by side
    assert snap1_id != snap2_id
    assert snap1_sha != snap2_sha
    assert (settings.cache_dir / f"{snap1_id}.gpkg").is_file()
    assert (settings.cache_dir / f"{snap1_id}.raw.json").is_file()
    assert (settings.cache_dir / f"{snap2_id}.gpkg").is_file()
    assert (settings.cache_dir / f"{snap2_id}.raw.json").is_file()

    # Job 1 still reproduces byte-for-byte after cache refresh!
    repro1 = client.post(f"/api/jobs/{job1}/reproduce")
    assert repro1.status_code == 200
    assert repro1.json()["matched"] is True


def test_data002_frozen_reproducibility_inputs_detect_or_isolate_mutations(tmp_path: Path) -> None:
    """DATA-002: Frozen style/corrections/templates allow reproduction after live file changes and detect tampering."""
    styles_dir = tmp_path / "live_styles"
    shutil.copytree(REPO_ROOT / "styles" / "mcy" / "v1", styles_dir / "mcy" / "v1")
    settings = _make_settings(tmp_path, MAPS4U_STYLE_DIR=styles_dir)
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Frozen Inputs Area"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "frozen-1",
        },
    ).json()["job_id"]
    assert client.post(f"/api/jobs/{job_id}/run").status_code == 200
    assert client.post(f"/api/jobs/{job_id}/approve", json={"reviewer": "rev1"}).status_code == 200

    # Mutate live style.yaml on disk -> reproduce() still succeeds using frozen copy after verifying hash
    live_style_path = styles_dir / "mcy" / "v1" / "style.yaml"
    style_data = yaml.safe_load(live_style_path.read_text(encoding="utf-8"))
    style_data["meta"]["notes"] = "Mutated live style on disk"
    live_style_path.write_text(yaml.safe_dump(style_data), encoding="utf-8")

    repro_ok = reproduce(job_id, settings, tmp_path / "repro_after_live_edit")
    assert repro_ok["matched"] is True

    # Tamper with the frozen style.yaml inside job's frozen_inputs/ -> reproduce() must reject with 409 E_STORAGE
    frozen_style_path = settings.artifact_dir / job_id / "frozen_inputs" / "style.yaml"
    frozen_style_path.write_text(yaml.safe_dump(style_data), encoding="utf-8")
    with pytest.raises(Maps4UError) as exc_info:
        reproduce(job_id, settings, tmp_path / "repro_after_tamper")
    assert exc_info.value.code == E_STORAGE
    assert exc_info.value.status_code == 409


def test_data003_geopackage_corruption_recovery_and_diagnostic_failure(tmp_path: Path) -> None:
    """DATA-003: Corrupted GeoPackage recovers from verified raw JSON or raises E_STORAGE instead of returning empty layers."""
    settings = _make_settings(tmp_path)
    bbox = BBox(min_lon=153.085, min_lat=-26.660, max_lon=153.105, max_lat=-26.645)
    classes = ["roads", "water", "water_lines", "parks", "boundaries", "coastline", "places", "landmarks"]
    extract = get_or_fetch(bbox=bbox, classes=classes, settings=settings)

    # Corrupt the .gpkg file with garbage bytes while raw .json remains valid -> auto-recovers!
    extract.gpkg_path.write_bytes(b"CORRUPTED-SQLITE-HEADER-GARBAGE")
    recovered = read_geopackage_snapshot(
        extract.gpkg_path,
        raw_fallback_path=extract.raw_path,
        expected_raw_sha256=extract.sha256,
    )
    assert len(recovered.roads) > 0

    # Corrupt .gpkg AND remove raw fallback -> must raise E_STORAGE (never silently return empty layers)
    extract.gpkg_path.write_bytes(b"CORRUPTED-AGAIN")
    with pytest.raises(Maps4UError) as exc_info:
        read_geopackage_snapshot(extract.gpkg_path, raw_fallback_path=tmp_path / "nonexistent.json")
    assert exc_info.value.code == E_STORAGE


def test_queue001_duplicate_dispatch_and_atomic_job_claiming(tmp_path: Path) -> None:
    """QUEUE-001: Duplicate Celery dispatches and concurrent worker executions on the same job are blocked."""
    settings = _make_settings(tmp_path, MAPS4U_QUEUE="celery")
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Queue001 Area"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "q001",
        },
    ).json()["job_id"]

    dispatched: list[str] = []
    with patch.object(run_job_task, "apply_async", side_effect=lambda *a, **kw: dispatched.append(job_id)):
        r1 = client.post(f"/api/jobs/{job_id}/run")
        assert r1.status_code == 200
        assert r1.json()["status"] == "queued"
        # Second dispatch while already queued must be rejected with 409
        r2 = client.post(f"/api/jobs/{job_id}/run")
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == E_STATE_ILLEGAL
        assert len(dispatched) == 1

    # Verify in-process atomic claim guard blocks concurrent execution
    assert try_acquire_job_claim(job_id) is True
    try:
        with pytest.raises(Maps4UError) as exc_info:
            execute_job_pipeline(job_id, settings)
        assert exc_info.value.code == E_STATE_ILLEGAL
        assert exc_info.value.status_code == 409
    finally:
        release_job_claim(job_id)


def test_queue002_retry_executes_or_enqueues_and_tracks_retry_count(tmp_path: Path) -> None:
    """QUEUE-002: Retry increments retry_count, preserves error history, and actually executes/enqueues."""
    settings = _make_settings(tmp_path, MAPS4U_QUEUE="inline")
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Queue002 Area"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "q002",
        },
    ).json()["job_id"]

    # Force a transient failure during acquiring
    with patch("maps4u.worker.executor.get_or_fetch", side_effect=RuntimeError("disk full transient")):
        r_fail = client.post(f"/api/jobs/{job_id}/run")
        assert r_fail.status_code == 500
    failed_state = client.get(f"/api/jobs/{job_id}").json()
    assert failed_state["status"] == "failed"
    assert failed_state["retry_count"] == 0

    # Calling /retry actually executes the job in inline mode and increments retry_count to 1
    r_retry = client.post(f"/api/jobs/{job_id}/retry")
    assert r_retry.status_code == 200
    retried_job = r_retry.json()
    assert retried_job["status"] == "proof_ready"
    assert retried_job["retry_count"] == 1


def test_queue003_celery_task_outcomes_distinguish_transient_and_terminal_errors(tmp_path: Path) -> None:
    """QUEUE-003: Celery task retries transient errors with backoff and raises on terminal failure."""
    settings = _make_settings(tmp_path, MAPS4U_QUEUE="celery")
    client = TestClient(create_app(settings))

    proj = client.post("/api/projects", json={"area_name": "Queue003 Area"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "q003",
        },
    ).json()["job_id"]

    overrides = {
        "MAPS4U_DATA_DIR": str(settings.maps4u_data_dir),
        "MAPS4U_DB_PATH": str(settings.db_path),
    }
    # 1. Transient error (E_OVERPASS_UNAVAILABLE) triggers self.retry and increments retry_count
    transient_err = Maps4UError(E_OVERPASS_UNAVAILABLE, "Overpass 503", status_code=503)
    with (
        patch("maps4u.worker.tasks.execute_job_pipeline", side_effect=transient_err),
        patch.object(run_job_task, "retry", side_effect=RuntimeError("CELERY_RETRY_TRIGGERED")),
        pytest.raises(RuntimeError, match="CELERY_RETRY_TRIGGERED"),
    ):
        run_job_task.run(job_id, settings_overrides=overrides)

    assert client.get(f"/api/jobs/{job_id}").json()["retry_count"] == 1

    # 2. Terminal error (E_QA_FAILED) raises Maps4UError instead of returning success
    terminal_err = Maps4UError(E_QA_FAILED, "Blocker QA failure", status_code=422)
    with (
        patch("maps4u.worker.tasks.execute_job_pipeline", side_effect=terminal_err),
        pytest.raises(Maps4UError) as exc_info,
    ):
        run_job_task.run(job_id, settings_overrides=overrides)
    assert exc_info.value.code == E_QA_FAILED


def test_qa001_no_runtime_qa_shortcuts_in_state_transitions(tmp_path: Path) -> None:
    """QA-001: Stubbing 'ok' into governed files without valid QA/PDF/manifest is always rejected."""
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    proj = client.post("/api/projects", json={"area_name": "QA001 Area"}).json()
    rev = client.post(f"/api/projects/{proj['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": proj["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "qa001",
        },
    ).json()["job_id"]

    job_dir = settings.artifact_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    for fname in GOVERNED_OUTPUT_FILES:
        (job_dir / fname).write_text("ok", encoding="utf-8")

    with db_session(settings.db_path) as conn:
        conn.execute("UPDATE jobs SET status = 'verifying' WHERE job_id = ?", (job_id,))
        with pytest.raises(Maps4UError) as exc_info:
            transition_job_state(
                conn,
                job_id=job_id,
                target_state="proof_ready",
                stage="verifying",
                event="attempt_shortcut",
                data_dir=settings.maps4u_data_dir,
                artifact_dir=settings.artifact_dir,
                enforce_qa=False,  # Even passing enforce_qa=False cannot bypass QA validation
            )
        assert exc_info.value.code == E_QA_FAILED


def test_ops001_meaningful_readiness_checks_db_broker_and_worker(tmp_path: Path) -> None:
    """OPS-001: /readyz checks SQLite DB, Redis broker, and Celery worker ping in celery mode."""
    celery_settings = _make_settings(
        tmp_path,
        MAPS4U_QUEUE="celery",
        MAPS4U_REDIS_URL="redis://127.0.0.1:63999/0",
    )
    client = TestClient(create_app(celery_settings))

    # Liveness (/healthz) is still 200
    assert client.get("/healthz").status_code == 200

    # Readiness (/readyz) fails with 503 when Redis broker is unreachable
    r_down = client.get("/readyz")
    assert r_down.status_code == 503
    body_down = r_down.json()
    assert body_down["ready"] is False
    assert body_down["database"] is True
    assert body_down["broker"] is False
    assert body_down["worker"] is False

    # When broker ping succeeds AND worker ping returns active worker dict -> 200 ready
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_inspector = MagicMock()
    mock_inspector.ping.return_value = {"celery@worker1": {"ok": "pong"}}
    with (
        patch("maps4u.api.routes_system.redis.Redis.from_url", return_value=mock_redis),
        patch("maps4u.api.routes_system.celery_app.control.inspect", return_value=mock_inspector),
    ):
        r_up = client.get("/readyz")
        assert r_up.status_code == 200
        body_up = r_up.json()
        assert body_up["ready"] is True
        assert body_up["broker"] is True
        assert body_up["worker"] is True


def test_cache_purge_protects_referenced_and_active_snapshots(tmp_path: Path) -> None:
    """Step C (R-14 / OD-8): Cache purge removes expired unreferenced snapshots while protecting referenced snapshots."""
    from maps4u.geo.cache import purge_expired_unreferenced_snapshots

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    # 1. Create and finalize a job so its OSM snapshot is referenced by a finalized job
    p = client.post("/api/projects", json={"area_name": "Purge Test"}).json()
    rev = client.post(f"/api/projects/{p['project_id']}/geofence", json=MCY_GEOFENCE).json()
    job_id = client.post(
        "/api/jobs",
        json={
            "project_id": p["project_id"],
            "geofence_revision": rev["revision_id"],
            "paper": "A4",
            "orientation": "landscape",
            "edition": "purge-1",
        },
    ).json()["job_id"]
    assert client.post(f"/api/jobs/{job_id}/run").status_code == 200
    assert client.post(f"/api/jobs/{job_id}/approve", json={"note": "Locked for print"}).status_code == 200
    mf = json.loads((settings.artifact_dir / job_id / "manifest.json").read_text(encoding="utf-8"))
    locked_snap_id = mf["provenance"]["snapshot_id"]
    assert locked_snap_id

    # 2. Age the locked snapshot to 120 days old and add two unreferenced snapshots:
    #    - snap_expired_unref (120 days old, not referenced by any job)
    #    - snap_fresh_unref (1 day old, not referenced by any job)
    cache_dir = settings.cache_dir
    exp_raw = cache_dir / "snap_expired_unref.raw.json"
    exp_gpkg = cache_dir / "snap_expired_unref.gpkg"
    exp_raw.write_text('{"elements": []}', encoding="utf-8")
    exp_gpkg.write_bytes(b"SQLite format 3\x00dummy")
    stale_ptr = cache_dir / "lookup_stale.latest.json"
    stale_ptr.write_text('{"lookup_key":"lookup_stale","snapshot_id":"snap_expired_unref"}', encoding="utf-8")

    fresh_raw = cache_dir / "snap_fresh_unref.raw.json"
    fresh_gpkg = cache_dir / "snap_fresh_unref.gpkg"
    fresh_raw.write_text('{"elements": []}', encoding="utf-8")
    fresh_gpkg.write_bytes(b"SQLite format 3\x00dummy")

    with db_session(settings.db_path) as conn:
        conn.execute(
            "UPDATE osm_snapshots SET fetched_at = '2020-01-01T00:00:00+00:00' WHERE snapshot_id = ?",
            (locked_snap_id,),
        )
        conn.execute(
            """
            INSERT INTO osm_snapshots (
                snapshot_id, bbox, fetched_at, source_url, raw_path, gpkg_path,
                osm_base_date, feature_counts_json, sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap_expired_unref",
                "-26.66,153.08,-26.64,153.10",
                "2020-01-01T00:00:00+00:00",
                "fixture://expired",
                str(exp_raw),
                str(exp_gpkg),
                "2020-01-01T00:00:00Z",
                "{}",
                "deadbeef",
            ),
        )
        conn.execute(
            """
            INSERT INTO osm_snapshots (
                snapshot_id, bbox, fetched_at, source_url, raw_path, gpkg_path,
                osm_base_date, feature_counts_json, sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap_fresh_unref",
                "-26.66,153.08,-26.64,153.10",
                "2099-01-01T00:00:00+00:00",
                "fixture://fresh",
                str(fresh_raw),
                str(fresh_gpkg),
                "2099-01-01T00:00:00Z",
                "{}",
                "cafebabe",
            ),
        )

    # 3. Dry run first: nothing deleted on disk yet
    dry_report = purge_expired_unreferenced_snapshots(
        db_path=settings.db_path,
        cache_dir=settings.cache_dir,
        artifact_dir=settings.artifact_dir,
        max_age_days=30,
        dry_run=True,
    )
    assert dry_report["dry_run"] is True
    assert "snap_expired_unref" in dry_report["purged_snapshot_ids"]
    assert locked_snap_id in dry_report["protected_referenced_ids"]
    assert "snap_fresh_unref" in dry_report["protected_unexpired_ids"]
    assert exp_raw.is_file()
    assert exp_gpkg.is_file()

    # 4. Execute live purge: expired unreferenced snapshot + stale pointer are removed, locked & fresh remain intact
    live_report = purge_expired_unreferenced_snapshots(
        db_path=settings.db_path,
        cache_dir=settings.cache_dir,
        artifact_dir=settings.artifact_dir,
        max_age_days=30,
        dry_run=False,
    )
    assert live_report["dry_run"] is False
    assert live_report["purged_snapshot_ids"] == ["snap_expired_unref"]
    assert locked_snap_id in live_report["protected_referenced_ids"]
    assert "snap_fresh_unref" in live_report["protected_unexpired_ids"]
    assert not exp_raw.exists()
    assert not exp_gpkg.exists()
    assert not stale_ptr.exists()
    assert fresh_raw.is_file()
    assert fresh_gpkg.is_file()

    # 5. Finalized job still reproduces 100% identically after cache purge!
    r_repro = client.post(f"/api/jobs/{job_id}/reproduce")
    assert r_repro.status_code == 200
    assert r_repro.json()["matched"] is True

    # 6. CLI entry point runs cleanly and emits JSON report
    import subprocess
    import sys

    cli_proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "purge_expired_cache.py"),
            "--data-dir",
            str(settings.maps4u_data_dir),
            "--max-age-days",
            "30",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_proc.returncode == 0
    cli_report = json.loads(cli_proc.stdout)
    assert cli_report["dry_run"] is True
    assert locked_snap_id in cli_report["protected_referenced_ids"]
