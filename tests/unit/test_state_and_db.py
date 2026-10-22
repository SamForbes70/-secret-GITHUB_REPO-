"""Unit tests for config, DB migration idempotency, state machine, and inline pipeline (S1.T1 & S1.T2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maps4u.core.config import Settings
from maps4u.core.db import db_session, run_migrations
from maps4u.core.errors import E_GOVERNED_OUTPUT_MISSING, E_STATE_ILLEGAL, Maps4UError
from maps4u.core.state import GOVERNED_OUTPUT_FILES, transition_job_state
from maps4u.render.canvas import GlyphPlacement, PathOps, RecordingCanvas, Stroke
from maps4u.worker.pipeline import PipelineRunner


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    first = run_migrations(db_path)
    assert first == [1]
    second = run_migrations(db_path)
    assert second == []


def test_state_machine_transitions_and_governed_outputs(test_settings: Settings) -> None:
    job_id = "maroochydore-2026-07-ed1"
    with db_session(test_settings.db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, area_name, geofence_geojson, paper, orientation, style_ref, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Maroochydore", "{}", "A4", "landscape", "mcy/v1", "created"),
        )
        # Illegal jump created -> proof_ready
        with pytest.raises(Maps4UError) as exc:
            transition_job_state(
                conn,
                job_id=job_id,
                target_state="proof_ready",
                stage="verifying",
                event="bad_jump",
                data_dir=test_settings.maps4u_data_dir,
                artifact_dir=test_settings.artifact_dir,
            )
        assert exc.value.code == E_STATE_ILLEGAL

        # Walk legal states up to verifying
        for st in [
            "validating",
            "queued",
            "assessing",
            "acquiring",
            "transforming",
            "styling",
            "labelling",
            "composing",
            "rendering",
            "verifying",
        ]:
            transition_job_state(
                conn,
                job_id=job_id,
                target_state=st,
                stage=st,
                event=f"enter_{st}",
                data_dir=test_settings.maps4u_data_dir,
                artifact_dir=test_settings.artifact_dir,
            )

        # Transition to proof_ready fails when governed outputs are missing
        with pytest.raises(Maps4UError) as gov_exc:
            transition_job_state(
                conn,
                job_id=job_id,
                target_state="proof_ready",
                stage="verifying",
                event="verified",
                data_dir=test_settings.maps4u_data_dir,
                artifact_dir=test_settings.artifact_dir,
            )
        assert gov_exc.value.code == E_GOVERNED_OUTPUT_MISSING

        # Create governed output files and verify proof_ready succeeds
        job_dir = test_settings.artifact_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        for fname in GOVERNED_OUTPUT_FILES:
            (job_dir / fname).write_text("ok", encoding="utf-8")

        new_state = transition_job_state(
            conn,
            job_id=job_id,
            target_state="proof_ready",
            stage="verifying",
            event="verified",
            data_dir=test_settings.maps4u_data_dir,
            artifact_dir=test_settings.artifact_dir,
        )
        assert new_state == "proof_ready"


def test_inline_pipeline_runner_happy_path(test_settings: Settings) -> None:
    job_id = "noosa-2026-07-ed1"
    with db_session(test_settings.db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, area_name, geofence_geojson, paper, orientation, style_ref, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Noosa", "{}", "A4", "landscape", "mcy/v1", "created"),
        )

    runner = PipelineRunner(test_settings)
    result = runner.run_stages(
        job_id,
        stages=[
            ("validating", lambda jid, ctx: {"validated": True}),
            ("queued", lambda jid, ctx: {"queued_ok": ctx["validated"]}),
        ],
    )
    assert result["validated"] is True
    assert result["queued_ok"] is True
    with db_session(test_settings.db_path) as conn:
        row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        assert row["status"] == "queued"


def test_recording_canvas_deterministic_drawlog(tmp_path: Path) -> None:
    c1 = RecordingCanvas()
    c1.set_page((297.0, 210.0), bleed_mm=3.0)
    c1.path(PathOps([("M", (10.0, 10.0)), ("L", (100.0, 50.0))]), Stroke("#333333", 1.2), None)
    c1.text([GlyphPlacement("Aerodrome Road", 20.0, 30.0, 0.0, "font-noto", 2.5)])
    pdf_path = tmp_path / "out" / "proof.pdf"
    c1.save_pdf(pdf_path)
    assert pdf_path.is_file()
    assert (tmp_path / "out" / "drawlog.json").is_file()
    assert len(c1.content_hash()) == 64
