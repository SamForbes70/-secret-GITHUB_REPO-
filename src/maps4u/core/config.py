"""Application settings loaded via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Canonical environment settings per §4.3."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    maps4u_data_dir: Path = Field(default=Path("./var"), alias="MAPS4U_DATA_DIR")
    maps4u_db_path: Path | None = Field(default=None, alias="MAPS4U_DB_PATH")
    maps4u_artifact_dir: Path | None = Field(default=None, alias="MAPS4U_ARTIFACT_DIR")
    maps4u_cache_dir: Path | None = Field(default=None, alias="MAPS4U_CACHE_DIR")
    maps4u_style_dir: Path = Field(default=Path("./styles"), alias="MAPS4U_STYLE_DIR")
    maps4u_default_style: str = Field(default="mcy/v1", alias="MAPS4U_DEFAULT_STYLE")
    maps4u_min_font_mm: float = Field(default=1.5, alias="MAPS4U_MIN_FONT_MM")
    maps4u_overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="MAPS4U_OVERPASS_URL",
    )
    maps4u_overpass_max_concurrency: int = Field(
        default=1, alias="MAPS4U_OVERPASS_MAX_CONCURRENCY"
    )
    maps4u_tile_url: str = Field(
        default="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        alias="MAPS4U_TILE_URL",
    )
    maps4u_cache_max_age_days: int = Field(default=0, alias="MAPS4U_CACHE_MAX_AGE_DAYS")
    maps4u_insets_enabled: bool = Field(default=True, alias="MAPS4U_INSETS_ENABLED")
    maps4u_operator_token: str = Field(default="", alias="MAPS4U_OPERATOR_TOKEN")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
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
