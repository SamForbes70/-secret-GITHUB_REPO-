"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from maps4u.core.config import Settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    cfg = settings or Settings()
    app = Celery(
        "maps4u",
        broker=cfg.redis_url,
        backend=cfg.redis_url,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_always_eager=(cfg.maps4u_queue == "inline"),
    )
    return app
