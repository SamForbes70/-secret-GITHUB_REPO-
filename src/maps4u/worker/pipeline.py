"""Stage pipeline runner supporting inline execution and exception recovery (S1.T2, BUG-009)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_PIPELINE_FAILED, Maps4UError
from maps4u.core.state import transition_job_state

StageCallable = Callable[[str, dict[str, Any]], dict[str, Any]]


class PipelineRunner:
    """Executes ordered pipeline stages with DB + JSONL audit transitions and exception recovery."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_stages(
        self,
        job_id: str,
        stages: list[tuple[str, StageCallable]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = dict(context or {})
        db_path: Path = self.settings.db_path
        data_dir: Path = self.settings.maps4u_data_dir
        artifact_dir: Path = self.settings.artifact_dir

        for target_state, handler in stages:
            try:
                with db_session(db_path) as conn:
                    transition_job_state(
                        conn,
                        job_id=job_id,
                        target_state=target_state,
                        stage=target_state,
                        event=f"stage_{target_state}_started",
                        data_dir=data_dir,
                        artifact_dir=artifact_dir,
                    )
                stage_output = handler(job_id, ctx)
                ctx.update(stage_output or {})
                with db_session(db_path) as conn:
                    conn.execute(
                        "INSERT INTO job_events (job_id, stage, event, payload_json) VALUES (?, ?, ?, ?)",
                        (job_id, target_state, f"stage_{target_state}_completed", "{}"),
                    )
            except Maps4UError as exc:
                with db_session(db_path) as conn:
                    transition_job_state(
                        conn,
                        job_id=job_id,
                        target_state="failed",
                        stage=target_state,
                        event="stage_failed",
                        data_dir=data_dir,
                        artifact_dir=artifact_dir,
                        payload=exc.details,
                        error_code=exc.code,
                        error_detail=exc.message,
                    )
                raise
            except Exception as exc:
                err_details = {
                    "stage": target_state,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
                err_msg = f"Unexpected failure during stage {target_state!r}: {type(exc).__name__}: {exc}"
                with db_session(db_path) as conn:
                    transition_job_state(
                        conn,
                        job_id=job_id,
                        target_state="failed",
                        stage=target_state,
                        event="stage_failed",
                        data_dir=data_dir,
                        artifact_dir=artifact_dir,
                        payload=err_details,
                        error_code=E_PIPELINE_FAILED,
                        error_detail=err_msg,
                    )
                raise Maps4UError(
                    E_PIPELINE_FAILED,
                    err_msg,
                    details=err_details,
                    status_code=500,
                ) from exc
        return ctx
