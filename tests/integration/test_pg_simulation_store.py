"""Integration tests for PgSimulationStore against a real PostgreSQL."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tests.integration.conftest import skip_no_db

pytestmark = [pytest.mark.integration, skip_no_db]


@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres"})
def test_save_and_get_run(clean_tables):
    from persistence.pg_simulation_store import PgSimulationStore

    store = PgSimulationStore()
    payload = {
        "model": "UTXO",
        "scenario": "coffee-export",
        "results": [{"chain_height": 3, "transaction_count": 5}],
    }

    run_id = store.save_run(payload)
    assert run_id.startswith("run-")

    retrieved = store.get_run(run_id)
    assert retrieved is not None
    assert retrieved["payload"]["model"] == "UTXO"
    assert retrieved["payload"]["scenario"] == "coffee-export"


@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres"})
def test_list_runs(clean_tables):
    from persistence.pg_simulation_store import PgSimulationStore

    store = PgSimulationStore()
    store.save_run({"model": "UTXO", "scenario": "s1", "results": []})
    store.save_run({"model": "ACCOUNT", "scenario": "s2", "results": [{}]})

    runs = store.list_runs(limit=10)
    assert len(runs) >= 2
    assert runs[0]["run_id"].startswith("run-")


@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres"})
def test_get_run_not_found(clean_tables):
    from persistence.pg_simulation_store import PgSimulationStore

    store = PgSimulationStore()
    assert store.get_run("run-nonexistent") is None
