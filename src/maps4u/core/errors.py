"""Maps4U error hierarchy and canonical error codes."""

from __future__ import annotations

from typing import Any


class Maps4UError(Exception):
    """Structured domain error with stable code and details."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


E_GEO_INVALID = "E_GEO_INVALID"
E_GEO_TOO_LARGE = "E_GEO_TOO_LARGE"
E_GEO_UNSUPPORTED = "E_GEO_UNSUPPORTED"
E_OVERPASS_UNAVAILABLE = "E_OVERPASS_UNAVAILABLE"
E_CORRECTIONS_INVALID = "E_CORRECTIONS_INVALID"
E_STYLE_INVALID = "E_STYLE_INVALID"
E_STATE_ILLEGAL = "E_STATE_ILLEGAL"
E_GOVERNED_OUTPUT_MISSING = "E_GOVERNED_OUTPUT_MISSING"
E_NOT_FOUND = "E_NOT_FOUND"
E_STORAGE = "E_STORAGE"
E_UNAUTHORIZED = "E_UNAUTHORIZED"
E_FORBIDDEN = "E_FORBIDDEN"
E_QA_FAILED = "E_QA_FAILED"
E_PIPELINE_FAILED = "E_PIPELINE_FAILED"
E_OSM_TRANSIENT = "E_OSM_TRANSIENT"
