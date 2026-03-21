from pathlib import Path

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.multiuser_wallet_store import JsonMultiUserWalletStore


def test_store_roundtrip(tmp_path):
    store_file: Path = tmp_path / "wallet-ledger.json"
    store = JsonMultiUserWalletStore(store_file)

    ledger = MultiUserWalletLedger()
    ledger.create_user("u-1", "User One")
    ledger.create_user("u-2", "User Two")
    ledger.create_wallet("u-1", wallet_id="w-1")
    ledger.create_wallet("u-2", wallet_id="w-2")
    ledger.mint("w-1", "10")
    ledger.set_user_policy("u-1", can_transfer=False, daily_limit="25")
    ledger.set_user_policy("u-1", can_transfer=True)
    ledger.set_user_risk_profile("u-1", profile_name="HIGH", transfer_alert_threshold="2")
    ledger.transfer("w-1", "w-2", "2", fee="0")

    revision_id = store.save_ledger(ledger)
    assert revision_id.startswith("rev-")
    assert store_file.exists()

    loaded = store.load_ledger()
    snapshot = loaded.state_snapshot()
    assert len(snapshot["users"]) == 2
    assert len(snapshot["wallets"]) == 2
    wallet_map = {wallet["wallet_id"]: wallet for wallet in snapshot["wallets"]}
    assert wallet_map["w-1"]["balance"] == "8.00000000"
    assert wallet_map["w-2"]["balance"] == "2.00000000"
    assert snapshot["policies"][0]["can_transfer"] is True
    assert snapshot["policies"][0]["daily_limit"] == "25.00000000"
    risk_map = {profile["user_id"]: profile for profile in snapshot["risk_profiles"]}
    assert risk_map["u-1"]["profile_name"] == "HIGH"
    assert len(snapshot["alerts"]) >= 1

    revisions = store.list_revisions(limit=5)
    assert len(revisions) == 1
    assert revisions[0]["revision_id"] == revision_id
