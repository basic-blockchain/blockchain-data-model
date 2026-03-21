#!/usr/bin/env python3
"""Simple forward-only SQL migration runner.

Reads versioned SQL files from migrations/versions/ and applies them
in order, skipping versions already recorded in schema_migrations.

Usage:
    DATABASE_URL=postgresql://user:pass@host:5432/db python migrations/migrate.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("psycopg2 is required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


VERSIONS_DIR = Path(__file__).resolve().parent / "versions"
FILE_PATTERN = re.compile(r"^V(\d+)__.*\.sql$")


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


def migrate(dsn: str | None = None) -> None:
    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("DATABASE_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)

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
                    cur.execute(sql)
                    print(f"  -> Applied successfully.")

                final = _current_version(cur)
                print(f"Migration complete. Current version: {final}.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
