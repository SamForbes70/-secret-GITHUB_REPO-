"""System health, readiness, and metadata endpoints (§7.1, OPS-001)."""

from __future__ import annotations

from typing import Any

import redis
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from maps4u import __version__
from maps4u.api.deps import get_settings
from maps4u.core.config import Settings, resolve_resource_path
from maps4u.core.db import db_session
from maps4u.core.schemas import MetaResponse
from maps4u.render.style_engine import list_available_styles
from maps4u.worker.tasks import celery_app

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Lightweight process liveness probe."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz", response_model=None)
def readyz(settings: Settings = Depends(get_settings)) -> dict[str, Any] | Response:
    """Deep operational readiness probe: verifies SQLite DB and, in celery mode, Redis broker + worker readiness (OPS-001)."""
    db_ok = False
    broker_ok: bool | None = None
    worker_ok: bool | None = None
    errors: list[str] = []

    try:
        with db_session(settings.db_path) as conn:
            conn.execute("SELECT 1").fetchone()
            conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        db_ok = True
    except Exception as exc:
        errors.append(f"database: {exc}")

    if settings.maps4u_queue == "celery":
        try:
            r_client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            broker_ok = bool(r_client.ping())
        except Exception as exc:
            broker_ok = False
            errors.append(f"broker: {exc}")

        if broker_ok:
            try:
                celery_app.conf.broker_url = settings.redis_url
                celery_app.conf.result_backend = settings.redis_url
                inspector = celery_app.control.inspect(timeout=1.0)
                pong = inspector.ping() if inspector is not None else None
                worker_ok = bool(pong)
                if not worker_ok:
                    errors.append("worker: no active Celery worker responded to ping")
            except Exception as exc:
                worker_ok = False
                errors.append(f"worker: {exc}")
        else:
            worker_ok = False

    ready = db_ok and (True if settings.maps4u_queue == "inline" else bool(broker_ok and worker_ok))
    payload: dict[str, Any] = {
        "ready": ready,
        "queue_mode": settings.maps4u_queue,
        "database": db_ok,
    }
    if settings.maps4u_queue == "celery":
        payload["broker"] = broker_ok
        payload["worker"] = worker_ok
    if errors:
        payload["errors"] = errors

    if not ready:
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/api/meta", response_model=MetaResponse)
def get_meta(settings: Settings = Depends(get_settings)) -> MetaResponse:
    schema_path = resolve_resource_path("schemas/style.schema.json", explicit_base=settings.maps4u_schema_dir)
    styles = list_available_styles(style_dir=settings.maps4u_style_dir, schema_path=schema_path)
    style_refs = [s.style_ref for s in styles] or [settings.maps4u_default_style]
    return MetaResponse(
        version=__version__,
        style_refs=style_refs,
        papers=["A3", "A4", "A5"],
        orientations=["landscape", "portrait"],
        thresholds={"min_font_mm": settings.maps4u_min_font_mm},
    )
