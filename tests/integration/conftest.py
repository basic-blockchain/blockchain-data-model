"""Shared fixtures for PostgreSQL integration tests."""

from __future__ import annotations

import os

import pytest

_has_psycopg2 = False
try:
    import psycopg2
    _has_psycopg2 = True
except ImportError:
    pass

pytestmark = pytest.mark.integration

INTEGRATION_DSN = os.environ.get("DATABASE_URL", "")


def _database_available() -> bool:
    if not _has_psycopg2 or not INTEGRATION_DSN:
        return False
    try:
        conn = psycopg2.connect(INTEGRATION_DSN)
        conn.close()
        return True
    except Exception:
        return False


skip_no_db = pytest.mark.skipif(
    not _database_available(),
    reason="PostgreSQL not available (set DATABASE_URL to enable)",
)


@pytest.fixture
def pg_conn():
    """Yield a psycopg2 connection that rolls back after each test."""
    conn = psycopg2.connect(INTEGRATION_DSN)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def clean_tables(pg_conn):
    """Truncate all application tables before a test."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE alerts, transfers, wallet_utxos, wallet_nonces,
                     user_risk_profiles, user_policies, wallets, users,
                     ledger_revisions, simulation_runs
            CASCADE
            """
        )
    pg_conn.commit()
