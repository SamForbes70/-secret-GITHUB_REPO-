"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request

from maps4u.core.config import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
