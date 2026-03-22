#!/usr/bin/env python3
"""Simple forward-only SQL migration runner with auto database creation.

Reads versioned SQL files from migrations/versions/ and applies them
in order, skipping versions already recorded in schema_migrations.
Creates the target database automatically if it does not exist.

Usage (Windows):
    set DATABASE_URL=postgresql://postgres:password@localhost:5432/blockchain_data_model
    py migrations/migrate.py

Usage (Linux/Mac):
    DATABASE_URL=postgresql://user:pass@host:5432/blockchain_data_model python migrations/migrate.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("psycopg2 is required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


VERSIONS_DIR = Path(__file__).resolve().parent / "versions"
FILE_PATTERN = re.compile(r"^V(\d+)__.*\.sql$")
DEFAULT_DB_NAME = "blockchain_data_model"


def _load_dotenv() -> None:
    """Load .env from project root, preserving explicit environment variables."""
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


def _parse_dsn(dsn: str) -> tuple[str, str]:
    """Extract the database name and build a maintenance DSN pointing to 'postgres'."""
    parsed = urlparse(dsn)
    db_name = parsed.path.lstrip("/") or DEFAULT_DB_NAME
    maintenance_parsed = parsed._replace(path="/postgres")
    maintenance_dsn = urlunparse(maintenance_parsed)
    return db_name, maintenance_dsn


def _ensure_database(dsn: str) -> None:
    """Create the target database if it does not exist."""
    db_name, maintenance_dsn = _parse_dsn(dsn)

    conn = psycopg2.connect(maintenance_dsn)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}"')
                print(f"Database '{db_name}' created.")
            else:
                print(f"Database '{db_name}' already exists.")
    finally:
        conn.close()


def _ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER      PRIMARY KEY,
            label      VARCHAR(100) NOT NULL,
            applied_at TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )


def _current_version(cur) -> int:
    cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
    return cur.fetchone()[0]


def _pending_files(current: int) -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for path in sorted(VERSIONS_DIR.glob("V*.sql")):
        match = FILE_PATTERN.match(path.name)
        if match:
            version = int(match.group(1))
            if version > current:
                files.append((version, path))
    return sorted(files, key=lambda x: x[0])


_RE_ADD_ENUM_VALUE = re.compile(
    r"^\s*ALTER\s+TYPE\s+\w+\s+ADD\s+VALUE\b",
    re.IGNORECASE | re.MULTILINE,
)


def _needs_autocommit(sql: str) -> bool:
    """ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL."""
    return bool(_RE_ADD_ENUM_VALUE.search(sql))


def _apply_autocommit(dsn: str, sql: str, label: str) -> None:
    """Execute SQL statements that require autocommit, one at a time.

    Tolerates duplicate-object errors so partially-applied migrations
    can be re-run safely (e.g. enum value or table already exists).
    """
    ac_conn = psycopg2.connect(dsn)
    ac_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with ac_conn.cursor() as cur:
            clean_lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
            clean_sql = "\n".join(clean_lines)
            for raw_stmt in clean_sql.split(";"):
                stmt = raw_stmt.strip()
                if not stmt:
                    continue
                try:
                    cur.execute(stmt)
                except psycopg2.errors.DuplicateObject:
                    print(f"  -> Skipped (already exists): {stmt[:60]}...")
                except psycopg2.errors.DuplicateTable:
                    print(f"  -> Skipped (table exists): {stmt[:60]}...")
                except psycopg2.errors.DuplicateColumn:
                    print(f"  -> Skipped (column exists): {stmt[:60]}...")
        print(f"  -> Applied {label} (autocommit).")
    finally:
        ac_conn.close()


def migrate(dsn: str | None = None) -> None:
    _load_dotenv()
    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("DATABASE_URL environment variable is required.", file=sys.stderr)
        print("Example: postgresql://postgres:password@localhost:5432/blockchain_data_model", file=sys.stderr)
        sys.exit(1)

    _ensure_database(dsn)

    conn = psycopg2.connect(dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                _ensure_migration_table(cur)
                current = _current_version(cur)
                pending = _pending_files(current)

                if not pending:
                    print(f"Database is up to date (version {current}).")
                    return

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            print(f"Applying {path.name} (version {version})...")

            if _needs_autocommit(sql):
                _apply_autocommit(dsn, sql, path.name)
            else:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        print(f"  -> Applied successfully.")

            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO schema_migrations (version, label) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (version, path.stem),
                    )

        with conn:
            with conn.cursor() as cur:
                final = _current_version(cur)
                print(f"Migration complete. Current version: {final}.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
