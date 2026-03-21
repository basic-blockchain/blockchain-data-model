from decimal import Decimal
from unittest.mock import patch

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def test_create_users_wallets_and_transfer_flow():
    ledger = MultiUserWalletLedger()

    assert "creado" in ledger.create_user("u-alice", "Alice")
    assert "creado" in ledger.create_user("u-bob", "Bob")

    msg_wallet_a = ledger.create_wallet("u-alice", wallet_id="wallet_user_alpha_01")
    msg_wallet_b = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    assert "creada" in msg_wallet_a["message"]
    assert "creada" in msg_wallet_b["message"]
    token_a = msg_wallet_a["auth_token"]

    assert "Mint" in ledger.mint("wallet_user_alpha_01", "100")
    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("100.00000000")

    tx = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "24.5",
        fee="0.5",
        reference="invoice-001",
        sender_token=token_a,
    )
    assert "Transferencia" in tx

    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("75.00000000")
    assert ledger.get_wallet_balance("wallet_user_bravo_02") == Decimal("24.50000000")
    assert len(ledger.state_snapshot()["transfers"]) == 2
    transfer_record = ledger.state_snapshot()["transfers"][1]
    assert transfer_record["nonce"] == 1
    assert transfer_record["previous_hash"] == "GENESIS"
    assert len(transfer_record["tx_hash"]) == 64


def test_transfer_rejects_insufficient_balance():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created_a = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "1")

    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "2",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    assert "Fondos insuficientes" in error or "fondos insuficientes" in error


def test_transfer_rejects_when_policy_disallows_sender():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created_a = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "20")

    assert "actualizada" in ledger.set_user_policy("u-a", can_transfer=False)
    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "5",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    assert "impide transferencias" in error


def test_transfer_rejects_when_daily_limit_is_exceeded():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created_a = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="10")
    assert "Transferencia" in ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "7",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "4",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    assert "límite diario excedido" in error


def test_transfer_uses_most_restrictive_daily_limit_between_policy_and_risk_profile():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created_a = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="20")
    assert "actualizado" in ledger.set_user_risk_profile("u-a", daily_limit="8")
    assert "Transferencia" in ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "7",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "2",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    assert "límite diario excedido" in error
    assert "Límite=8.00000000" in error


def test_transfer_generates_alerts_for_configured_thresholds():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created_a = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "100")

    assert "actualizado" in ledger.set_user_risk_profile(
        "u-a",
        transfer_alert_threshold="5",
        daily_alert_threshold="9",
    )

    assert "Transferencia" in ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "6",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    alerts = ledger.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "TRANSFER_THRESHOLD"

    assert "Transferencia" in ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "4",
        fee="0",
        sender_token=created_a["auth_token"],
    )
    alerts = ledger.list_alerts()
    assert len(alerts) == 2
    assert alerts[0]["type"] == "DAILY_THRESHOLD"


def test_set_risk_profile_applies_named_defaults():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")

    assert "actualizado" in ledger.set_user_risk_profile("u-a", profile_name="restricted")
    profile = ledger.get_user_risk_profile("u-a")
    assert profile["profile_name"] == "RESTRICTED"
    assert profile["daily_limit"] == "1000.00000000"
    assert profile["transfer_alert_threshold"] == "300.00000000"


def test_create_wallet_rejects_invalid_id_format_or_length():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")

    error = ledger.create_wallet("u-a", wallet_id="ab")
    assert error == "Wallet invalida. Usa 20-30 caracteres: letras, numeros, '-' o '_'."


def test_wallet_token_rotates_every_120_seconds_on_access():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=100):
        created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
        assert "creada" in created["message"]
        first = created["auth_token"]

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=219):
        same = ledger.list_wallets(user_id="u-a")[0]["auth_token"]
    assert same == first

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=220):
        rotated = ledger.list_wallets(user_id="u-a")[0]["auth_token"]
    assert rotated != first


def test_transfer_requires_sender_token():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "5")

    error = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "1", fee="0")
    assert "sender_token es requerido" in error


def test_transfer_rejects_invalid_sender_token():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "5")

    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "1",
        fee="0",
        sender_token="INVALIDTOKEN1",
    )
    assert "token inválido" in error


def test_transfer_rejects_expired_sender_token_and_rotates_it():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=100):
        created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
        ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
        ledger.mint("wallet_user_alpha_01", "5")

    old_token = created["auth_token"]
    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=221):
        error = ledger.transfer(
            "wallet_user_alpha_01",
            "wallet_user_bravo_02",
            "1",
            fee="0",
            sender_token=old_token,
        )

    assert "token expirado" in error
    refreshed = ledger.list_wallets(user_id="u-a")[0]["auth_token"]
    assert refreshed != old_token


def test_refresh_wallet_token_allows_owner_even_with_mismatch_or_expired_token():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=100):
        created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")

    old_token = created["auth_token"]
    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=240):
        refreshed = ledger.refresh_wallet_token(
            "u-a",
            "wallet_user_alpha_01",
            current_token="WRONGTOKEN123",
        )

    assert refreshed["wallet_id"] == "wallet_user_alpha_01"
    assert refreshed["previous_token_matches"] is False
    assert refreshed["previous_token_expired"] is True
    assert refreshed["auth_token"] != old_token


def test_refresh_wallet_token_rejects_non_owner():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")

    error = ledger.refresh_wallet_token("u-b", "wallet_user_alpha_01")
    assert "no es propietario" in error


def test_transfer_rejects_invalid_expected_nonce():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "5")

    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "1",
        fee="0",
        sender_token=created["auth_token"],
        expected_nonce=2,
    )
    assert "nonce inválido" in error


def test_verify_transfer_integrity_detects_hash_tampering():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "10")

    assert "Transferencia" in ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "2",
        fee="0",
        sender_token=created["auth_token"],
    )
    assert ledger.verify_transfer_integrity()["valid"] is True

    ledger.transfers[-1]["tx_hash"] = "0" * 64
    report = ledger.verify_transfer_integrity()
    assert report["valid"] is False
    assert "Hash de transferencia inválido" in report["reason"]


def test_utxo_transfer_flow_updates_balances_and_utxos():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01", model="UTXO")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02", model="UTXO")

    assert "Mint" in ledger.mint("wallet_user_alpha_01", "10")
    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("10.00000000")

    tx = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "3",
        fee="1",
        sender_token=created["auth_token"],
    )
    assert "Transferencia" in tx
    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("6.00000000")
    assert ledger.get_wallet_balance("wallet_user_bravo_02") == Decimal("3.00000000")
    assert len(ledger.list_utxos("wallet_user_bravo_02")) == 1


def test_transfer_rejects_between_different_models():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    created = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01", model="ACCOUNT")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02", model="UTXO")
    ledger.mint("wallet_user_alpha_01", "5")

    error = ledger.transfer(
        "wallet_user_alpha_01",
        "wallet_user_bravo_02",
        "1",
        fee="0",
        sender_token=created["auth_token"],
    )
    assert "distinto modelo" in error
