"""Tests for persistence abstract interfaces and ABC inheritance."""

from __future__ import annotations

from persistence.interfaces import SimulationRunRepository, WalletLedgerRepository
from persistence.multiuser_wallet_store import JsonMultiUserWalletStore
from persistence.simulation_store import JsonSimulationStore


def test_json_wallet_store_is_wallet_repository():
    assert issubclass(JsonMultiUserWalletStore, WalletLedgerRepository)


def test_json_simulation_store_is_simulation_repository():
    assert issubclass(JsonSimulationStore, SimulationRunRepository)


def test_wallet_repository_has_required_methods():
    methods = {"load_ledger", "save_ledger", "list_revisions"}
    abstract = {m for m in WalletLedgerRepository.__abstractmethods__}
    assert methods == abstract


def test_simulation_repository_has_required_methods():
    methods = {"save_run", "list_runs", "get_run"}
    abstract = {m for m in SimulationRunRepository.__abstractmethods__}
    assert methods == abstract
