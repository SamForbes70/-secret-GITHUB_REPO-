"""Celery tasks entrypoint."""

from __future__ import annotations

from typing import Any

from maps4u.core.config import Settings
from maps4u.worker.celery_app import create_celery_app

celery_app = create_celery_app()


@celery_app.task(name="maps4u.run_job")
def run_job_task(job_id: str) -> dict[str, Any]:
    settings = Settings()
    return {"job_id": job_id, "queue_mode": settings.maps4u_queue, "status": "dispatched"}
