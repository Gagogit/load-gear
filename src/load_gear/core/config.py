"""Application configuration loaded from YAML + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "configs"


class DatabaseConfig(BaseModel):
    url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/loadgear"
    echo: bool = False
    pool_size: int = 5


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    log_level: str = "info"


class StorageConfig(BaseModel):
    backend: str = "local"
    base_path: str = "storage"


class AppConfig(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    server: ServerConfig = ServerConfig()
    storage: StorageConfig = StorageConfig()


def load_config() -> AppConfig:
    """Load config from configs/app.yaml with env var overrides."""
    config_path = CONFIG_DIR / "app.yaml"

    data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    # Environment variable overrides
    if db_url := os.environ.get("DATABASE_URL"):
        data.setdefault("database", {})["url"] = db_url

    return AppConfig(**data)


# Singleton
_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config
