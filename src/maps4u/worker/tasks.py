"""Celery task definitions with bounded retry and accurate failure outcomes (QUEUE-002, QUEUE-003)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from celery import Celery

from maps4u.core.config import Settings
from maps4u.core.db import db_session
from maps4u.core.errors import E_OSM_TRANSIENT, E_OVERPASS_UNAVAILABLE, Maps4UError
from maps4u.core.logging import append_audit_jsonl
from maps4u.worker.executor import execute_job_pipeline

TRANSIENT_ERROR_CODES: frozenset[str] = frozenset({E_OSM_TRANSIENT, E_OVERPASS_UNAVAILABLE})


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


@celery_app.task(bind=True, name="maps4u.run_job", max_retries=2, default_retry_delay=2)
def run_job_task(
    self: Any,
    job_id: str,
    settings_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the governed pipeline in Celery; raise on failure for accurate task state (QUEUE-003)."""
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
        now_iso = datetime.now(UTC).isoformat()
        current_retries = int(getattr(self.request, "retries", 0) or 0)
        max_retries = int(getattr(self, "max_retries", 2) or 2)

        if err.code in TRANSIENT_ERROR_CODES and current_retries < max_retries:
            backoff_s = min(60, 2 ** (current_retries + 1))
            with db_session(cfg.db_path) as conn:
                conn.execute(
                    "UPDATE jobs SET retry_count = COALESCE(retry_count, 0) + 1, updated_at = ? WHERE job_id = ?",
                    (now_iso, job_id),
                )
                conn.execute(
                    "INSERT INTO job_events (job_id, ts, stage, event, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        job_id,
                        now_iso,
                        "queued",
                        "celery_task_retry_scheduled",
                        json.dumps(
                            {
                                "attempt": current_retries + 1,
                                "max_retries": max_retries,
                                "backoff_s": backoff_s,
                                "error_code": err.code,
                                "error_detail": err.message,
                            },
                            sort_keys=True,
                        ),
                    ),
                )
            append_audit_jsonl(
                cfg.maps4u_data_dir,
                {
                    "ts": now_iso,
                    "event": "celery_task_retry_scheduled",
                    "job_id": job_id,
                    "attempt": current_retries + 1,
                    "backoff_s": backoff_s,
                    "error_code": err.code,
                },
            )
            raise self.retry(exc=err, countdown=backoff_s) from err

        with db_session(cfg.db_path) as conn:
            conn.execute(
                "INSERT INTO job_events (job_id, ts, stage, event, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    job_id,
                    now_iso,
                    "failed",
                    "celery_task_failed",
                    json.dumps(
                        {
                            "error_code": err.code,
                            "error_detail": err.message,
                            "retries": current_retries,
                        },
                        sort_keys=True,
                    ),
                ),
            )
        append_audit_jsonl(
            cfg.maps4u_data_dir,
            {
                "ts": now_iso,
                "event": "celery_task_failed",
                "job_id": job_id,
                "error_code": err.code,
                "error_detail": err.message,
                "retries": current_retries,
            },
        )
        raise
