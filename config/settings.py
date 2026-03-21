"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    persistence_backend: str
    pg_dsn: str
    pg_pool_min: int
    pg_pool_max: int


def get_settings() -> Settings:
    return Settings(
        persistence_backend=os.environ.get("PERSISTENCE_BACKEND", "json"),
        pg_dsn=os.environ.get("DATABASE_URL", ""),
        pg_pool_min=int(os.environ.get("PG_POOL_MIN", "1")),
        pg_pool_max=int(os.environ.get("PG_POOL_MAX", "5")),
    )
