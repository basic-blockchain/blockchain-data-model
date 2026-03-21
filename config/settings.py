"""Application settings loaded from .env file and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_LOADED = False


def _load_dotenv() -> None:
    """Load .env file from the project root if it exists."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    persistence_backend: str
    pg_dsn: str
    pg_pool_min: int
    pg_pool_max: int


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        persistence_backend=os.environ.get("PERSISTENCE_BACKEND", "json"),
        pg_dsn=os.environ.get("DATABASE_URL", ""),
        pg_pool_min=int(os.environ.get("PG_POOL_MIN", "1")),
        pg_pool_max=int(os.environ.get("PG_POOL_MAX", "5")),
    )
