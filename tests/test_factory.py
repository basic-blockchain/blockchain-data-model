"""Tests for persistence factory backend selection."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest

from persistence.factory import create_simulation_store, create_wallet_store
from persistence.interfaces import SimulationRunRepository, WalletLedgerRepository
from persistence.multiuser_wallet_store import JsonMultiUserWalletStore
from persistence.simulation_store import JsonSimulationStore

_has_psycopg2 = importlib.util.find_spec("psycopg2") is not None


def test_create_wallet_store_json_default(tmp_path):
    store = create_wallet_store(json_path=tmp_path / "ledger.json")
    assert isinstance(store, JsonMultiUserWalletStore)
    assert isinstance(store, WalletLedgerRepository)


def test_create_simulation_store_json_default(tmp_path):
    store = create_simulation_store(json_path=tmp_path / "runs.json")
    assert isinstance(store, JsonSimulationStore)
    assert isinstance(store, SimulationRunRepository)


def test_create_wallet_store_json_requires_path():
    with pytest.raises(ValueError, match="json_path is required"):
        create_wallet_store(json_path=None)


def test_create_simulation_store_json_requires_path():
    with pytest.raises(ValueError, match="json_path is required"):
        create_simulation_store(json_path=None)


@pytest.mark.skipif(not _has_psycopg2, reason="psycopg2 not installed")
@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres", "DATABASE_URL": "postgresql://x"})
def test_create_wallet_store_postgres_returns_pg_instance():
    from persistence.pg_multiuser_wallet_store import PgMultiUserWalletStore

    store = create_wallet_store()
    assert isinstance(store, PgMultiUserWalletStore)
    assert isinstance(store, WalletLedgerRepository)


@pytest.mark.skipif(not _has_psycopg2, reason="psycopg2 not installed")
@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres", "DATABASE_URL": "postgresql://x"})
def test_create_simulation_store_postgres_returns_pg_instance():
    from persistence.pg_simulation_store import PgSimulationStore

    store = create_simulation_store()
    assert isinstance(store, PgSimulationStore)
    assert isinstance(store, SimulationRunRepository)
