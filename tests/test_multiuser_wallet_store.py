from pathlib import Path
import json

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.multiuser_wallet_store import JsonMultiUserWalletStore


def test_store_roundtrip(tmp_path):
    store_file: Path = tmp_path / "wallet-ledger.json"
    store = JsonMultiUserWalletStore(store_file)

    ledger = MultiUserWalletLedger()
    ledger.create_user("u-1", "User One")
    ledger.create_user("u-2", "User Two")
    created_u1 = ledger.create_wallet("u-1", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-2", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "10")
    ledger.set_user_policy("u-1", can_transfer=False, daily_limit="25")
    ledger.set_user_policy("u-1", can_transfer=True)
    ledger.set_user_risk_profile("u-1", profile_name="HIGH", transfer_alert_threshold="2")
    ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "2",
        fee="0",
        sender_token=created_u1["auth_token"],
    )

    revision_id = store.save_ledger(ledger)
    assert revision_id.startswith("rev-")
    assert store_file.exists()

    loaded = store.load_ledger()
    snapshot = loaded.state_snapshot()
    assert len(snapshot["users"]) == 2
    assert len(snapshot["wallets"]) == 2
    wallet_map = {wallet["wallet_id"]: wallet for wallet in snapshot["wallets"]}
    assert wallet_map["wallet_user_alpha_01"]["balance"] == "8.00000000"
    assert wallet_map["wallet_user_bravo_02"]["balance"] == "2.00000000"
    assert snapshot["policies"][0]["can_transfer"] is True
    assert snapshot["policies"][0]["daily_limit"] == "25.00000000"
    risk_map = {profile["user_id"]: profile for profile in snapshot["risk_profiles"]}
    assert risk_map["u-1"]["profile_name"] == "HIGH"
    assert len(snapshot["alerts"]) >= 1

    revisions = store.list_revisions(limit=5)
    assert len(revisions) == 1
    assert revisions[0]["revision_id"] == revision_id


def test_store_load_infers_wallet_nonce_for_legacy_transfers(tmp_path):
    store_file: Path = tmp_path / "wallet-ledger.json"
    legacy_doc = {
        "schema_version": 1,
        "updated_at": "2026-03-21T00:00:00+00:00",
        "current_revision_id": "rev-legacy",
        "snapshot": {
            "users": [
                {"user_id": "u-1", "display_name": "User One", "created_at": "2026-03-21T00:00:00+00:00"},
                {"user_id": "u-2", "display_name": "User Two", "created_at": "2026-03-21T00:00:00+00:00"},
            ],
            "wallets": [
                {
                    "wallet_id": "wallet_user_alpha_01",
                    "user_id": "u-1",
                    "currency": "USDX",
                    "balance": "8.00000000",
                    "auth_token": "ABCDEFGHIJKLMNOP",
                    "token_issued_at": 100,
                    "created_at": "2026-03-21T00:00:00+00:00",
                },
                {
                    "wallet_id": "wallet_user_bravo_02",
                    "user_id": "u-2",
                    "currency": "USDX",
                    "balance": "2.00000000",
                    "auth_token": "QRSTUVWXYZ123456",
                    "token_issued_at": 100,
                    "created_at": "2026-03-21T00:00:00+00:00",
                },
            ],
            "policies": [],
            "risk_profiles": [],
            "transfers": [
                {
                    "transfer_id": "tx-legacy-1",
                    "type": "TRANSFER",
                    "sender_wallet": "wallet_user_alpha_01",
                    "receiver_wallet": "wallet_user_bravo_02",
                    "amount": "1.00000000",
                    "fee": "0.00000000",
                    "reference": "legacy-1",
                    "status": "SETTLED",
                    "created_at": "2026-03-21T00:00:01+00:00",
                },
                {
                    "transfer_id": "tx-legacy-2",
                    "type": "TRANSFER",
                    "sender_wallet": "wallet_user_alpha_01",
                    "receiver_wallet": "wallet_user_bravo_02",
                    "amount": "1.00000000",
                    "fee": "0.00000000",
                    "reference": "legacy-2",
                    "status": "SETTLED",
                    "created_at": "2026-03-21T00:00:02+00:00",
                },
            ],
            "alerts": [],
        },
        "revisions": [],
    }
    store_file.write_text(json.dumps(legacy_doc), encoding="utf-8")

    store = JsonMultiUserWalletStore(store_file)
    ledger = store.load_ledger()

    assert ledger.current_wallet_nonce("wallet_user_alpha_01") == 2


def test_store_roundtrip_with_utxo_wallets(tmp_path):
    store_file: Path = tmp_path / "wallet-ledger.json"
    store = JsonMultiUserWalletStore(store_file)

    ledger = MultiUserWalletLedger()
    ledger.create_user("u-1", "User One")
    ledger.create_user("u-2", "User Two")
    created_u1 = ledger.create_wallet("u-1", wallet_id="wallet_user_alpha_01", model="UTXO")
    ledger.create_wallet("u-2", wallet_id="wallet_user_bravo_02", model="UTXO")
    ledger.mint("wallet_user_alpha_01", "10")
    ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "3",
        fee="1",
        sender_token=created_u1["auth_token"],
    )

    store.save_ledger(ledger)
    loaded = store.load_ledger()

    assert loaded.get_wallet_balance("wallet_user_alpha_01") == loaded.wallets["wallet_user_alpha_01"].balance
    assert loaded.wallets["wallet_user_alpha_01"].model == "UTXO"
    assert loaded.wallets["wallet_user_bravo_02"].model == "UTXO"
    assert loaded.get_wallet_balance("wallet_user_alpha_01").to_eng_string() == "6.00000000"
    assert loaded.get_wallet_balance("wallet_user_bravo_02").to_eng_string() == "3.00000000"
