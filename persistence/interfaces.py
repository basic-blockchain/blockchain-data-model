"""Abstract interfaces for persistence repositories (Repository Pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


class WalletLedgerRepository(ABC):
    """Persistence contract for the multi-user wallet ledger."""

    @abstractmethod
    def load_ledger(self) -> MultiUserWalletLedger: ...

    @abstractmethod
    def save_ledger(self, ledger: MultiUserWalletLedger) -> str: ...

    @abstractmethod
    def list_revisions(self, limit: int = 20) -> list[dict]: ...


class SimulationRunRepository(ABC):
    """Persistence contract for simulation run records."""

    @abstractmethod
    def save_run(self, run_payload: dict) -> str: ...

    @abstractmethod
    def list_runs(self, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def get_run(self, run_id: str) -> dict | None: ...
