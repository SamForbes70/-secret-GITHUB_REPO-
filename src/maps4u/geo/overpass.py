"""Overpass QL builder and client with retry/backoff ladder and offline fixture support."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import httpx

from maps4u.core.errors import E_OVERPASS_UNAVAILABLE, Maps4UError
from maps4u.core.models import BBox

CLASS_CLAUSES: dict[str, list[str]] = {
    "roads": ['way["highway"]'],
    "water": ['way["natural"="water"]', 'way["waterway"="riverbank"]', 'way["landuse"="reservoir"]'],
    "water_lines": ['way["waterway"~"^(river|stream|canal)$"]'],
    "parks": ['way["leisure"~"^(park|nature_reserve)$"]', 'way["landuse"~"^(recreation_ground|forest)$"]'],
    "boundaries": ['way["boundary"="administrative"]["admin_level"~"^(9|10)$"]'],
    "coastline": ['way["natural"="coastline"]'],
    "places": ['node["place"~"^(suburb|locality|town|hamlet)$"]', 'node["tourism"]', 'node["natural"~"^(peak|cape)$"]'],
    "landmarks": ['node["man_made"~"^(tower|lighthouse)$"]', 'node["historic"]'],
}


def build_overpass_query(
    bbox: BBox,
    classes: list[str],
    timeout: int = 120,
) -> str:
    """Build a deterministic Overpass QL query for a normalised bbox and sorted class list."""
    ov_bbox = bbox.to_overpass_bbox(precision=6)
    clauses: list[str] = []
    for cls_name in sorted(set(classes)):
        for expr in CLASS_CLAUSES.get(cls_name, []):
            clauses.append(f"  {expr}({ov_bbox});")
    nl = chr(10)
    body = nl.join(clauses)
    return f"[out:json][timeout:{timeout}];{nl}({nl}{body}{nl});{nl}(._;>;);{nl}out body;"


def _default_http_transport(
    url: str,
    query: str,
) -> bytes:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, data={"data": query})
        resp.raise_for_status()
        return resp.content


class OverpassClient:
    """Overpass client supporting file:// fixtures and 3-attempt backoff ladder (ADR-5)."""

    def __init__(
        self,
        endpoint_url: str,
        retry_backoff: tuple[float, ...] = (10.0, 30.0, 90.0),
        transport: Callable[[str, str], bytes] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.retry_backoff = retry_backoff
        self.transport = transport or _default_http_transport
        self.sleep_fn = sleep_fn

    def fetch_raw(
        self,
        query: str,
    ) -> bytes:
        if self.endpoint_url.startswith("file://"):
            fixture_path = Path(self.endpoint_url.removeprefix("file://"))
            if not fixture_path.is_file():
                raise Maps4UError(
                    E_OVERPASS_UNAVAILABLE,
                    f"Overpass fixture file not found: {fixture_path}",
                )
            return fixture_path.read_bytes()

        max_attempts = len(self.retry_backoff)
        last_err: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return self.transport(self.endpoint_url, query)
            except Exception as exc:
                last_err = exc
                if attempt + 1 < max_attempts:
                    self.sleep_fn(self.retry_backoff[attempt])
        raise Maps4UError(
            E_OVERPASS_UNAVAILABLE,
            f"Overpass API unavailable after {max_attempts} attempts: {last_err}",
            details={
                "endpoint": self.endpoint_url,
                "attempts": max_attempts,
            },
            status_code=503,
        )
