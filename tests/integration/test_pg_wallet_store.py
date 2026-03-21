"""Integration tests for PgMultiUserWalletStore against a real PostgreSQL."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tests.integration.conftest import skip_no_db

pytestmark = [pytest.mark.integration, skip_no_db]


@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres"})
def test_save_and_load_roundtrip(clean_tables):
    from domain.multiuser_wallet_ledger import MultiUserWalletLedger
    from persistence.pg_multiuser_wallet_store import PgMultiUserWalletStore

    store = PgMultiUserWalletStore()
    ledger = MultiUserWalletLedger()

    ledger.create_user("u-alice", "Alice")
    token = ledger.create_wallet("u-alice", "w-alice", "ACCOUNT", "USDX")
    ledger.mint("w-alice", "100.00000000", reference="seed")

    revision_id = store.save_ledger(ledger)
    assert revision_id.startswith("rev-")

    loaded = store.load_ledger()
    assert loaded.wallets["w-alice"].balance == ledger.wallets["w-alice"].balance
    assert len(loaded.transfers) == len(ledger.transfers)
    assert "u-alice" in loaded.users


@patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgres"})
def test_list_revisions(clean_tables):
    from domain.multiuser_wallet_ledger import MultiUserWalletLedger
    from persistence.pg_multiuser_wallet_store import PgMultiUserWalletStore

    store = PgMultiUserWalletStore()
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")

    store.save_ledger(ledger)
    store.save_ledger(ledger)

    revisions = store.list_revisions(limit=10)
    assert len(revisions) >= 2
    assert "revision_id" in revisions[0]
    assert "users" in revisions[0]
