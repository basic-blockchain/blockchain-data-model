from decimal import Decimal

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def test_create_users_wallets_and_transfer_flow():
    ledger = MultiUserWalletLedger()

    assert "creado" in ledger.create_user("u-alice", "Alice")
    assert "creado" in ledger.create_user("u-bob", "Bob")

    msg_wallet_a = ledger.create_wallet("u-alice", wallet_id="w-alice")
    msg_wallet_b = ledger.create_wallet("u-bob", wallet_id="w-bob")
    assert "creada" in msg_wallet_a
    assert "creada" in msg_wallet_b

    assert "Mint" in ledger.mint("w-alice", "100")
    assert ledger.get_wallet_balance("w-alice") == Decimal("100.00000000")

    tx = ledger.transfer("w-alice", "w-bob", "24.5", fee="0.5", reference="invoice-001")
    assert "Transferencia" in tx

    assert ledger.get_wallet_balance("w-alice") == Decimal("75.00000000")
    assert ledger.get_wallet_balance("w-bob") == Decimal("24.50000000")
    assert len(ledger.state_snapshot()["transfers"]) == 2


def test_transfer_rejects_insufficient_balance():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "1")

    error = ledger.transfer("wa", "wb", "2", fee="0")
    assert "Fondos insuficientes" in error or "fondos insuficientes" in error


def test_transfer_rejects_when_policy_disallows_sender():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "20")

    assert "actualizada" in ledger.set_user_policy("u-a", can_transfer=False)
    error = ledger.transfer("wa", "wb", "5", fee="0")
    assert "impide transferencias" in error


def test_transfer_rejects_when_daily_limit_is_exceeded():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="10")
    assert "Transferencia" in ledger.transfer("wa", "wb", "7", fee="0")
    error = ledger.transfer("wa", "wb", "4", fee="0")
    assert "límite diario excedido" in error


def test_transfer_uses_most_restrictive_daily_limit_between_policy_and_risk_profile():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "50")

    assert "actualizada" in ledger.set_user_policy("u-a", daily_limit="20")
    assert "actualizado" in ledger.set_user_risk_profile("u-a", daily_limit="8")
    assert "Transferencia" in ledger.transfer("wa", "wb", "7", fee="0")
    error = ledger.transfer("wa", "wb", "2", fee="0")
    assert "límite diario excedido" in error
    assert "Límite=8.00000000" in error


def test_transfer_generates_alerts_for_configured_thresholds():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "100")

    assert "actualizado" in ledger.set_user_risk_profile(
        "u-a",
        transfer_alert_threshold="5",
        daily_alert_threshold="9",
    )

    assert "Transferencia" in ledger.transfer("wa", "wb", "6", fee="0")
    alerts = ledger.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "TRANSFER_THRESHOLD"

    assert "Transferencia" in ledger.transfer("wa", "wb", "4", fee="0")
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
