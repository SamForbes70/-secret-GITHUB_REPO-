"""Application settings loaded via pydantic-settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGED_RESOURCES_DIR = PACKAGE_ROOT / "resources"
SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_resource_path(relative_path: str | Path, explicit_base: Path | None = None) -> Path:
    """Resolve config, schema, or style resource path safely across source, Docker (/app), and wheel installs."""
    rel = Path(relative_path)
    if rel.is_absolute():
        return rel

    candidates: list[Path] = []
    if explicit_base is not None:
        candidates.append(explicit_base / rel)
        if rel.parts and explicit_base.name == rel.parts[0]:
            candidates.append(explicit_base.joinpath(*rel.parts[1:]))

    # Check environment overrides for top-level resource directories
    if rel.parts:
        top = rel.parts[0]
        sub = Path(*rel.parts[1:]) if len(rel.parts) > 1 else Path()
        env_map = {
            "config": os.environ.get("MAPS4U_CONFIG_DIR"),
            "schemas": os.environ.get("MAPS4U_SCHEMA_DIR"),
            "styles": os.environ.get("MAPS4U_STYLE_DIR"),
        }
        env_dir = env_map.get(top)
        if env_dir:
            candidates.append(Path(env_dir) / sub)
            candidates.append(Path(env_dir) / rel)

    candidates.extend(
        [
            SOURCE_REPO_ROOT / rel,
            Path.cwd() / rel,
            Path("/app") / rel,
            PACKAGED_RESOURCES_DIR / rel,
        ]
    )
    for cand in candidates:
        if cand.exists():
            return cand
    return PACKAGED_RESOURCES_DIR / rel


class Settings(BaseSettings):
    """Canonical environment settings per §4.3."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        populate_by_name=True,
    )

    maps4u_data_dir: Path = Field(default=Path("./var"), alias="MAPS4U_DATA_DIR")
    maps4u_db_path: Path | None = Field(default=None, alias="MAPS4U_DB_PATH")
    maps4u_artifact_dir: Path | None = Field(default=None, alias="MAPS4U_ARTIFACT_DIR")
    maps4u_cache_dir: Path | None = Field(default=None, alias="MAPS4U_CACHE_DIR")
    maps4u_config_dir: Path = Field(
        default_factory=lambda: resolve_resource_path("config"),
        alias="MAPS4U_CONFIG_DIR",
    )
    maps4u_schema_dir: Path = Field(
        default_factory=lambda: resolve_resource_path("schemas"),
        alias="MAPS4U_SCHEMA_DIR",
    )
    maps4u_style_dir: Path = Field(
        default_factory=lambda: resolve_resource_path("styles"),
        alias="MAPS4U_STYLE_DIR",
    )
    maps4u_default_style: str = Field(default="mcy/v1", alias="MAPS4U_DEFAULT_STYLE")
    maps4u_min_font_mm: float = Field(default=1.5, alias="MAPS4U_MIN_FONT_MM")
    maps4u_overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="MAPS4U_OVERPASS_URL",
    )
    maps4u_overpass_timeout_s: int = Field(
        default=120, alias="MAPS4U_OVERPASS_TIMEOUT_S"
    )
    maps4u_overpass_max_concurrency: int = Field(
        default=1, alias="MAPS4U_OVERPASS_MAX_CONCURRENCY"
    )
    maps4u_tile_url: str = Field(
        default="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        alias="MAPS4U_TILE_URL",
    )
    maps4u_cache_max_age_days: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "MAPS4U_CACHE_MAX_AGE_DAYS",
            "MAPS4U_OSM_CACHE_TTL_DAYS",
            "maps4u_cache_max_age_days",
            "maps4u_osm_cache_ttl_days",
        ),
    )
    maps4u_insets_enabled: bool = Field(default=True, alias="MAPS4U_INSETS_ENABLED")
    maps4u_operator_token: str = Field(default="", alias="MAPS4U_OPERATOR_TOKEN")
    maps4u_reviewer_token: str = Field(default="", alias="MAPS4U_REVIEWER_TOKEN")
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("MAPS4U_REDIS_URL", "REDIS_URL", "redis_url", "maps4u_redis_url"),
    )
    maps4u_queue: Literal["inline", "celery"] = Field(default="inline", alias="MAPS4U_QUEUE")
    maps4u_render_dpi: int = Field(default=300, alias="MAPS4U_RENDER_DPI")
    maps4u_log_level: str = Field(default="INFO", alias="MAPS4U_LOG_LEVEL")
    maps4u_env: Literal["dev", "test", "staging", "prod"] = Field(
        default="dev", alias="MAPS4U_ENV"
    )

    @model_validator(mode="after")
    def _resolve_derived_paths(self) -> Settings:
        if self.maps4u_db_path is None:
            self.maps4u_db_path = self.maps4u_data_dir / "maps4u.sqlite3"
        if self.maps4u_artifact_dir is None:
            self.maps4u_artifact_dir = self.maps4u_data_dir / "jobs"
        if self.maps4u_cache_dir is None:
            self.maps4u_cache_dir = self.maps4u_data_dir / "osm_cache"
        return self

    @property
    def maps4u_redis_url(self) -> str:
        return self.redis_url

    @property
    def db_path(self) -> Path:
        assert self.maps4u_db_path is not None
        return self.maps4u_db_path

    @property
    def artifact_dir(self) -> Path:
        assert self.maps4u_artifact_dir is not None
        return self.maps4u_artifact_dir

    @property
    def cache_dir(self) -> Path:
        assert self.maps4u_cache_dir is not None
        return self.maps4u_cache_dir

    def ensure_dirs(self) -> None:
        self.maps4u_data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
