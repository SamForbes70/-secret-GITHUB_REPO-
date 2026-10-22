from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from maps4u.core.config import Settings
from maps4u.core.db import run_migrations

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture(autouse=True)
def _no_network_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live") is not None:
        return
    real_connect = socket.socket.connect
    def guarded_connect(self: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and len(address) >= 1:
            if str(address[0]) in {"127.0.0.1", "localhost", "::1"}:
                return real_connect(self, address)
        raise RuntimeError(f"External network blocked in offline test (§11.3): {address!r}")
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    fixture_path = FIXTURES_DIR / "overpass" / "mcy_sample.json"
    settings = Settings(
        MAPS4U_DATA_DIR=tmp_path / "var",
        MAPS4U_OVERPASS_URL=f"file://{fixture_path}",
        MAPS4U_QUEUE="inline",
        MAPS4U_ENV="test",
    )
    settings.ensure_dirs()
    run_migrations(settings.db_path)
    return settings
