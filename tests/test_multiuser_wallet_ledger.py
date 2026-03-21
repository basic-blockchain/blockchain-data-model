from decimal import Decimal
from unittest.mock import patch

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def test_create_users_wallets_and_transfer_flow():
    ledger = MultiUserWalletLedger()

    assert "creado" in ledger.create_user("u-alice", "Alice")
    assert "creado" in ledger.create_user("u-bob", "Bob")

    msg_wallet_a = ledger.create_wallet("u-alice", wallet_id="wallet_user_alpha_01")
    msg_wallet_b = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    assert "creada" in msg_wallet_a
    assert "creada" in msg_wallet_b

    assert "Mint" in ledger.mint("wallet_user_alpha_01", "100")
    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("100.00000000")

    tx = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "24.5", fee="0.5", reference="invoice-001")
    assert "Transferencia" in tx

    assert ledger.get_wallet_balance("wallet_user_alpha_01") == Decimal("75.00000000")
    assert ledger.get_wallet_balance("wallet_user_bravo_02") == Decimal("24.50000000")
    assert len(ledger.state_snapshot()["transfers"]) == 2


def test_transfer_rejects_insufficient_balance():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "1")

    error = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "2", fee="0")
    assert "Fondos insuficientes" in error or "fondos insuficientes" in error


def test_transfer_rejects_when_policy_disallows_sender():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "20")

    assert "actualizada" in ledger.set_user_policy("u-a", can_transfer=False)
    error = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "5", fee="0")
    assert "impide transferencias" in error


def test_transfer_rejects_when_daily_limit_is_exceeded():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="10")
    assert "Transferencia" in ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "7", fee="0")
    error = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "4", fee="0")
    assert "límite diario excedido" in error


def test_transfer_uses_most_restrictive_daily_limit_between_policy_and_risk_profile():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="20")
    assert "actualizado" in ledger.set_user_risk_profile("u-a", daily_limit="8")
    assert "Transferencia" in ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "7", fee="0")
    error = ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "2", fee="0")
    assert "límite diario excedido" in error
    assert "Límite=8.00000000" in error


def test_transfer_generates_alerts_for_configured_thresholds():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02")
    ledger.mint("wallet_user_alpha_01", "100")

    assert "actualizado" in ledger.set_user_risk_profile(
        "u-a",
        transfer_alert_threshold="5",
        daily_alert_threshold="9",
    )

    assert "Transferencia" in ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "6", fee="0")
    alerts = ledger.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "TRANSFER_THRESHOLD"

    assert "Transferencia" in ledger.transfer("wallet_user_alpha_01", "wallet_user_bravo_02", "4", fee="0")
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


def test_wallet_token_rotates_every_10_seconds_on_access():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=100):
        assert "creada" in ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01")
        first = ledger.list_wallets(user_id="u-a")[0]["auth_token"]

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=109):
        same = ledger.list_wallets(user_id="u-a")[0]["auth_token"]
    assert same == first

    with patch.object(MultiUserWalletLedger, "_now_epoch", return_value=110):
        rotated = ledger.list_wallets(user_id="u-a")[0]["auth_token"]
    assert rotated != first
