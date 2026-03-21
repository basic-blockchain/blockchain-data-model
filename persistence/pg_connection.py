"""PostgreSQL connection pool management (lazy singleton)."""

from __future__ import annotations

from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool

from config.settings import get_settings

_pool: pg_pool.ThreadedConnectionPool | None = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.pg_dsn:
            raise RuntimeError(
                "DATABASE_URL environment variable is required for PostgreSQL backend"
            )
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=settings.pg_pool_min,
            maxconn=settings.pg_pool_max,
            dsn=settings.pg_dsn,
        )
    return _pool


@contextmanager
def get_connection():
    """Yield a connection from the pool with auto commit/rollback."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_pool() -> None:
    """Close all connections in the pool."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
