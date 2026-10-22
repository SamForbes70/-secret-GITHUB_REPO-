"""Structured JSON logging and append-only JSONL audit log writer."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit single-line JSON log records."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for extra_key in ("job_id", "stage", "event", "duration_ms", "details"):
            val = getattr(record, extra_key, None)
            if val is not None:
                payload[extra_key] = val
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: str = "INFO") -> None:
    """Configure root maps4u logger with structured JSON formatting."""
    logger = logging.getLogger("maps4u")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


def append_audit_jsonl(data_dir: Path, record: dict[str, Any]) -> Path:
    """Append a structured audit event to {data_dir}/audit/events.jsonl."""
    audit_dir = data_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "events.jsonl"
    safe_record = {"ts": datetime.now(UTC).isoformat(), **record}
    with audit_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(safe_record, sort_keys=True) + "\n")
    return audit_file
