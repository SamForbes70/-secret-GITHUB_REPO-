"""Celery application and task definitions (BUG-004, BUG-005)."""

from __future__ import annotations

from typing import Any

from celery import Celery

from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_NOT_FOUND, Maps4UError
from maps4u.worker.executor import execute_job_pipeline


def make_celery(settings: Settings | None = None) -> Celery:
    cfg = settings or Settings()
    app = Celery("maps4u", broker=cfg.redis_url, backend=cfg.redis_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
    )
    return app


celery_app = make_celery()


@celery_app.task(bind=True, name="maps4u.run_job", max_retries=2, default_retry_delay=5)
def run_job_task(
    self: Any,
    job_id: str,
    settings_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the governed map production pipeline for job_id inside the Celery worker."""
    cfg = Settings(**(settings_overrides or {}))
    celery_app.conf.broker_url = cfg.redis_url
    celery_app.conf.result_backend = cfg.redis_url

    try:
        result = execute_job_pipeline(job_id, cfg)
        return {
            "job_id": job_id,
            "queue_mode": cfg.maps4u_queue,
            **result,
        }
    except Maps4UError as err:
        if err.code == E_NOT_FOUND:
            raise
        with db_session(cfg.db_path) as conn:
            row = conn.execute("SELECT status, error_code, error_detail FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            status = str(row["status"]) if row else "failed"
        return {
            "job_id": job_id,
            "queue_mode": cfg.maps4u_queue,
            "status": status,
            "error_code": err.code,
            "error_detail": err.message,
        }
