from pathlib import Path

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.multiuser_wallet_store import JsonMultiUserWalletStore


def test_store_roundtrip(tmp_path):
    store_file: Path = tmp_path / "wallet-ledger.json"
    store = JsonMultiUserWalletStore(store_file)

    ledger = MultiUserWalletLedger()
    ledger.create_user("u-1", "User One")
    ledger.create_wallet("u-1", wallet_id="w-1")
    ledger.mint("w-1", "10")
    ledger.set_user_policy("u-1", can_transfer=False, daily_limit="25")

    revision_id = store.save_ledger(ledger)
    assert revision_id.startswith("rev-")
    assert store_file.exists()

    loaded = store.load_ledger()
    snapshot = loaded.state_snapshot()
    assert len(snapshot["users"]) == 1
    assert len(snapshot["wallets"]) == 1
    assert snapshot["wallets"][0]["balance"] == "10.00000000"
    assert snapshot["policies"][0]["can_transfer"] is False
    assert snapshot["policies"][0]["daily_limit"] == "25.00000000"

    revisions = store.list_revisions(limit=5)
    assert len(revisions) == 1
    assert revisions[0]["revision_id"] == revision_id
