"""FastAPI application factory for Maps4U."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from maps4u import __version__
from maps4u.api.routes_jobs import router as jobs_router
from maps4u.api.routes_projects import router as projects_router
from maps4u.api.routes_styles import router as styles_router
from maps4u.api.routes_system import router as system_router
from maps4u.core.config import Settings
from maps4u.core.db import run_migrations
from maps4u.core.errors import Maps4UError
from maps4u.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    cfg.ensure_dirs()
    configure_logging(cfg.maps4u_log_level)
    run_migrations(cfg.db_path)

    app = FastAPI(
        title="Maps4U Street Map Production API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = cfg

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    @app.exception_handler(Maps4UError)
    async def _handle_maps4u_error(_request: Request, exc: Maps4UError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.include_router(system_router)
    app.include_router(projects_router)
    app.include_router(jobs_router)
    app.include_router(styles_router)
    return app

