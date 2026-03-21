"""Factory functions for persistence backend selection (Strategy Pattern)."""

from __future__ import annotations

from pathlib import Path

from config.settings import get_settings
from persistence.interfaces import SimulationRunRepository, WalletLedgerRepository


def create_wallet_store(json_path: Path | None = None) -> WalletLedgerRepository:
    """Return a WalletLedgerRepository for the configured backend."""
    settings = get_settings()
    if settings.persistence_backend == "postgres":
        from persistence.pg_multiuser_wallet_store import PgMultiUserWalletStore

        return PgMultiUserWalletStore()
    from persistence.multiuser_wallet_store import JsonMultiUserWalletStore

    if json_path is None:
        raise ValueError("json_path is required for JSON backend")
    return JsonMultiUserWalletStore(json_path)


def create_simulation_store(
    json_path: Path | None = None,
) -> SimulationRunRepository:
    """Return a SimulationRunRepository for the configured backend."""
    settings = get_settings()
    if settings.persistence_backend == "postgres":
        from persistence.pg_simulation_store import PgSimulationStore

        return PgSimulationStore()
    from persistence.simulation_store import JsonSimulationStore

    if json_path is None:
        raise ValueError("json_path is required for JSON backend")
    return JsonSimulationStore(json_path)
